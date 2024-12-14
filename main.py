import aiohttp, json, os, asyncio, logging
import apscheduler
import apscheduler.schedulers
import apscheduler.schedulers.asyncio
from astrbot.api.all import Context, AstrMessageEvent, CommandResult

class Main:
    def __init__(self, context: Context) -> None:
        self.NAMESPACE = "astrbot_plugin_leetcode"
        self.context = context
        self.logger = logging.getLogger("astrbot")
        self.context.register_commands(self.NAMESPACE, "lcd", "leetcode 每日一题", 1, self.daily_problem)
        self.context.register_commands(self.NAMESPACE, "lcr", "leetcode 随机题目", 1, self.random_problem)
        self.context.register_commands(self.NAMESPACE, "lcauto", "启动/关闭每日 9 点发送每日一题", 1, self.auto_daily_problem)
        self.scheduler = apscheduler.schedulers.asyncio.AsyncIOScheduler()
        # self.started

        # 加载订阅了每日一题的会话号
        if not os.path.exists(f"data/{self.NAMESPACE}_data.json"):
            with open(f"data/{self.NAMESPACE}_data.json", "w") as f:
                json.dump({}, f)
        with open(f"data/{self.NAMESPACE}_data.json", "r") as f:
            self.data = json.load(f)
        self.lc_auto_daily_ids = self.data.get("lc_auto_daily_ids", [])
        
        if self.lc_auto_daily_ids:
            self._start_cron_if_not()
    
    def _start_cron_if_not(self):
        '''启动定时任务'''
        if not self.scheduler.get_jobs():
            self.scheduler.add_job(self._send_daily_problem, "cron", hour=9, minute=0)
            self.scheduler.start()
    
    async def _send_daily_problem(self):
        '''自动发送每日一题'''
        self.logger.info(f"正在推送 Leetcode 每日一题给 {len(self.lc_auto_daily_ids)} 个会话...")
        question_id, title_cn, difficulty, problem, url = await self._get_daily_problem()
        for session_id in self.lc_auto_daily_ids:
            image_url = await self.context.image_renderer.render(f"""## Leetcode Daily: {question_id}.{title_cn} ({difficulty})\n---\n{problem}\n---\n链接: {url}""", return_url=True)
            await self.context.send_message(session_id, CommandResult().url_image(image_url))
            await self.context.send_message(session_id, CommandResult().message(f"新鲜的题出炉了喵，快写喵！\n链接: {url}"))
            await asyncio.sleep(1)

    async def auto_daily_problem(self, message: AstrMessageEvent, context: Context):
        '''启动/关闭每日 9 点发送每日一题'''
        umo_id = message.unified_msg_origin
        
        opened = False
        if umo_id in self.lc_auto_daily_ids:
            self.lc_auto_daily_ids.remove(umo_id)
        else:
            self.lc_auto_daily_ids.append(umo_id)
            opened = True
        
        self.data["lc_auto_daily_ids"] = self.lc_auto_daily_ids
        with open(f"data/{self.NAMESPACE}_data.json", "w") as f:
            json.dump(self.data, f)
        
        self._start_cron_if_not()
            
        if opened: return CommandResult().message(f"已对 {umo_id} 开启每日一题")
        return CommandResult().message(f"已对 {umo_id} 关闭每日一题")
        
    async def _graphql(self, query: str):
        '''发送 graphql 请求'''
        async with aiohttp.ClientSession() as session:
            async with session.post("https://leetcode.cn/graphql", json=json.loads(query)) as response:
                ret = await response.json()
                return ret
            
    async def _get_problem(self, problem_slug: str):
        '''获取题目内容'''
        query = r'{"query":"    query questionTranslations($titleSlug: String!) {  question(titleSlug: $titleSlug) {    translatedTitle    translatedContent  }}    ","variables":{"titleSlug":"{%slug}"},"operationName":"questionTranslations"}'
        query = query.replace(r"{%slug}", problem_slug)
        return await self._graphql(query)
    
    async def _get_daily_problem(self):
        '''获取每日一题'''
        query = r'{"query":"    query questionOfToday {  todayRecord {    date    userStatus    question {      questionId      frontendQuestionId: questionFrontendId      difficulty      title      titleCn: translatedTitle      titleSlug      paidOnly: isPaidOnly      freqBar      isFavor      acRate      status      solutionNum      hasVideoSolution      topicTags {        name        nameTranslated: translatedName        id      }      extra {        topCompanyTags {          imgUrl          slug          numSubscribed        }      }    }    lastSubmission {      id    }  }}    ","variables":{},"operationName":"questionOfToday"}'
        data = (await self._graphql(query))['data']['todayRecord'][0]['question']
        difficulty = data['difficulty']
        title_cn = data['titleCn']
        question_id = data['frontendQuestionId']
        slug = data['titleSlug']
        url = f"https://leetcode.cn/problems/{slug}"
        problem = (await self._get_problem(slug))['data']['question']['translatedContent']
        return (question_id, title_cn, difficulty, problem, url)
    
    async def daily_problem(self, message: AstrMessageEvent, context: Context):
        '''每日一题'''
        question_id, title_cn, difficulty, problem, url = await self._get_daily_problem()
        return CommandResult().use_t2i(True) \
                        .message(f"""## Leetcode Daily: {question_id}.{title_cn} ({difficulty})\n---\n{problem}\n---\n链接: {url}""")

    async def random_problem(self, message: AstrMessageEvent, context: Context):
        query = r'{"query":"    query problemsetRandomFilteredQuestion($categorySlug: String!, $filters: QuestionListFilterInput) {  problemsetRandomFilteredQuestion(categorySlug: $categorySlug, filters: $filters)}    ","variables":{"categorySlug":"all-code-essentials","filters":{}},"operationName":"problemsetRandomFilteredQuestion"}'
        data = (await self._graphql(query))
        slug = data['data']['problemsetRandomFilteredQuestion']
        problem = (await self._get_problem(slug))['data']['question']['translatedContent']
        url = f"https://leetcode.cn/problems/{slug}"
        return CommandResult().use_t2i(True) \
                        .message(f"""## Leetcode Random\n---\n{problem}\n---\n链接: {url}""")
