import tempfile
import imgkit

import aiohttp
import apscheduler
import apscheduler.schedulers
import apscheduler.schedulers.asyncio
import asyncio
import json
import logging
import os

from markdown2 import markdown

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
        img_path = self._markdown_to_temp_image(
            f"""## Leetcode Daily: {question_id}.{title_cn} ({difficulty})\n---\n{problem}\n---\n链接: {url}""")
        for session_id in self.lc_auto_daily_ids:
            # image_url = await self.context.image_renderer.render(f"""## Leetcode Daily: {question_id}.{title_cn} ({difficulty})\n---\n{problem}\n---\n链接: {url}""", return_url=True)
            await self.context.send_message(session_id, CommandResult().file_image(img_path))
            await self.context.send_message(session_id, CommandResult().message(f"新鲜的题出炉了喵，快写喵！\n链接: {url}"))
            await asyncio.sleep(1)
        os.remove(img_path)

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
        img_path = self._markdown_to_temp_image(
            f"""## Leetcode Daily: {question_id}.{title_cn} ({difficulty})\n---\n{problem}\n---\n链接: {url}""")
        return CommandResult().file_image(img_path)

    async def random_problem(self, message: AstrMessageEvent, context: Context):
        query = r'{"query":"    query problemsetRandomFilteredQuestion($categorySlug: String!, $filters: QuestionListFilterInput) {  problemsetRandomFilteredQuestion(categorySlug: $categorySlug, filters: $filters)}    ","variables":{"categorySlug":"all-code-essentials","filters":{}},"operationName":"problemsetRandomFilteredQuestion"}'
        data = (await self._graphql(query))
        slug = data['data']['problemsetRandomFilteredQuestion']
        problem = (await self._get_problem(slug))['data']['question']['translatedContent']
        url = f"https://leetcode.cn/problems/{slug}"
        return CommandResult().use_t2i(True) \
                        .message(f"""## Leetcode Random\n---\n{problem}\n---\n链接: {url}""")

    def _markdown_to_temp_image(self, markdown_content: str) -> str:
        """
           将 Markdown 渲染为 HTML 后，使用 imgkit 转换为 PNG，并保存到临时文件。
           返回临时文件的文件名（路径）。
           """
        # 将 Markdown 转 HTML
        html_body = markdown(markdown_content)

        # 包装完整的 HTML 内容，添加基础样式
        html_content = f"""
           <!DOCTYPE html>
           <html>
               <head>
                   <meta charset="utf-8">
                   <style>
                       body {{
                           font-family: Arial, sans-serif;
                           margin: 20px;
                       }}
                       h1 {{ color: #0096FF; }}
                       p, li {{ color: #333333; line-height: 1.5; }}
                       a {{ color: #FF4500; text-decoration: none; }}
                   </style>
               </head>
               <body>
                   {html_body}
               </body>
           </html>
           """

        # 创建临时文件来保存图片
        with tempfile.NamedTemporaryFile(suffix=".png", delete=False) as tmp_file:
            temp_file_name = tmp_file.name  # 获取临时文件名

        # 转换为 PNG 并保存
        imgkit.from_string(html_content, temp_file_name, options={
            'format': 'png',
            'width': 800,
            'disable-smart-width': ''  # 使内容固定宽度
        })

        # 返回生成的临时文件路径
        return temp_file_name



