import aiohttp, json
import textwrap
from util.plugin_dev.api.v1.bot import Context, AstrMessageEvent, CommandResult
from util.plugin_dev.api.v1.config import *

class Main:
    def __init__(self, context: Context) -> None:
        self.NAMESPACE = "astrbot_plugin_leetcode"
        self.context = context
        self.context.register_commands(self.NAMESPACE, "lc每日", "leetcode 每日一题", 1, self.daily_problem)
        self.context.register_commands(self.NAMESPACE, "lc随机", "leetcode 随机题目", 1, self.random_problem)

    async def _graphql(self, query: str):
        async with aiohttp.ClientSession() as session:
            async with session.post("https://leetcode.cn/graphql", json=json.loads(query)) as response:
                ret = await response.json()
                return ret
            
    async def _get_problem(self, problem_slug: str):
        query = r'{"query":"    query questionTranslations($titleSlug: String!) {  question(titleSlug: $titleSlug) {    translatedTitle    translatedContent  }}    ","variables":{"titleSlug":"{%slug}"},"operationName":"questionTranslations"}'
        query = query.replace(r"{%slug}", problem_slug)
        return await self._graphql(query)
    
    async def daily_problem(self, message: AstrMessageEvent, context: Context):
        query = r'{"query":"    query questionOfToday {  todayRecord {    date    userStatus    question {      questionId      frontendQuestionId: questionFrontendId      difficulty      title      titleCn: translatedTitle      titleSlug      paidOnly: isPaidOnly      freqBar      isFavor      acRate      status      solutionNum      hasVideoSolution      topicTags {        name        nameTranslated: translatedName        id      }      extra {        topCompanyTags {          imgUrl          slug          numSubscribed        }      }    }    lastSubmission {      id    }  }}    ","variables":{},"operationName":"questionOfToday"}'
        data = (await self._graphql(query))['data']['todayRecord'][0]['question']
        difficulty = data['difficulty']
        title_cn = data['titleCn']
        question_id = data['frontendQuestionId']
        slug = data['titleSlug']
        url = f"https://leetcode.cn/problems/{slug}"
        problem = (await self._get_problem(slug))['data']['question']['translatedContent']
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