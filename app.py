"""A Discord bot for Nine Grids."""

import logging
import os
from enum import Enum, auto, unique
from re import sub
from typing import Any, Coroutine, Dict
from urllib.parse import parse_qs, urlparse

from bs4 import BeautifulSoup
from discord import ButtonStyle, Intents, Interaction, TextStyle, ui
from discord.ext import commands, tasks
from dotenv import load_dotenv
from requests import Session

# 讀取 .env
load_dotenv()

# 設定 logger
handler = logging.StreamHandler()
logger = logging.getLogger("discord")
logger.addHandler(handler)

# 設定 bot 的 intents
intents = Intents.default()
intents.message_content = True
bot = commands.Bot(command_prefix="!", intents=intents)

# 宣告各種變數、常數
DELETE_TIME = 600
sessions: Dict[int, Session] = {}
all_tasks: Dict[int, Dict[int, tasks.Loop[Coroutine[Any, Any, None]]]] = {}
NINE_GRID_URL = "http://ninegrids.csie.ncu.edu.tw"
NINE_GRID_IP = "http://140.115.59.182"

login_url = f"{NINE_GRID_IP}/p/users/sign_in"
logout_url = f"{NINE_GRID_IP}/p/users/sign_out"
quiz_url = f"{NINE_GRID_IP}/quizzes"
query_url = f"{NINE_GRID_IP}/answers?quiz="
judge_url = f"{NINE_GRID_IP}/judgements"


class LoginModal(ui.Modal, title="Login"):
    """登入的 Modal。"""

    username = ui.TextInput(label="Username", placeholder="輸入使用者名稱(學號)")
    password = ui.TextInput(label="Password", placeholder="輸入密碼")

    async def on_submit(self, interaction: Interaction, /):
        """登入。"""

        user_id = interaction.user.id
        _login(user_id, self.username.value, self.password.value)

        if user := _is_login(user_id):
            self.clear_items()
            await interaction.response.edit_message(
                content=f"{user} 登入成功！", view=self
            )
        else:
            await interaction.response.edit_message(content="登入失敗！")


class JudgeModal(ui.Modal, title="Judge"):
    """批改的 Modal。"""

    def __init__(self, data: Dict):
        super().__init__()
        self.data = data

    content = ui.TextInput(
        label="Content",
        placeholder="輸入 Content(可空白)",
        style=TextStyle.paragraph,
        required=False,
    )

    async def on_submit(self, interaction: Interaction, /):
        """提交。"""

        self.data["judgement[content]"] = self.content.value
        await _submit_judgement(interaction, self)


class LoginView(ui.View):
    """登入的 View。"""

    def __init__(self, label: str = "登入"):
        super().__init__()
        self.login_button = ui.Button(label=label, style=ButtonStyle.primary)
        self.login_button.callback = self.login
        self.add_item(self.login_button)

    async def login(self, interaction: Interaction):
        """顯示登入對話框。"""
        await interaction.response.send_modal(LoginModal())


class LogoutView(ui.View):
    """登出的 View。"""

    @ui.button(label="登出", style=ButtonStyle.danger)
    async def logout(self, interaction: Interaction, _: ui.Button):
        """登出。"""

        user_id = interaction.user.id
        _logout(user_id)

        if user := _is_login(user_id):
            await interaction.response.edit_message(content=f"{user} 登出失敗！")
        else:
            self.clear_items()
            await interaction.response.edit_message(content="登出成功！", view=self)


class JudgeView(ui.View):
    """批改的 View。"""

    def __init__(self, answer_id: str, csrf_token: str, timeout: int = DELETE_TIME):
        super().__init__(timeout=timeout)
        self.answer_id = answer_id
        self.data = {
            "utf8": "✓",
            "authenticity_token": csrf_token,
            "judgement[answer_id]": answer_id,
            "judgement[content]": "",
            "judgement[result]": "",
            "button": "",
        }

    @ui.button(label="通過", style=ButtonStyle.success, row=1)
    async def passed(self, interaction: Interaction, _: ui.Button):
        """通過。"""

        self.data["judgement[result]"] = "pass"
        await _submit_judgement(interaction, self)

    @ui.button(label="通過(備註)", style=ButtonStyle.success, row=1)
    async def passed_with_content(self, interaction: Interaction, _: ui.Button):
        """通過（含備註）。"""

        self.data["judgement[result]"] = "pass"
        await interaction.response.send_modal(JudgeModal(self.data))

    @ui.button(label="拒絕", style=ButtonStyle.danger, row=2)
    async def rejected(self, interaction: Interaction, _: ui.Button):
        """拒絕。"""

        self.data["judgement[result]"] = "reject"
        await _submit_judgement(interaction, self)

    @ui.button(label="拒絕(備註)", style=ButtonStyle.danger, row=2)
    async def rejected_with_content(self, interaction: Interaction, _: ui.Button):
        """拒絕（含備註）。"""

        self.data["judgement[result]"] = "reject"
        await interaction.response.send_modal(JudgeModal(self.data))


class StopTaskView(ui.View):
    """停止定期取得指定問題的繳交答案的 View。"""

    def __init__(self, user_tasks: Dict[int, tasks.Loop[Coroutine[Any, Any, None]]]):
        super().__init__()
        self.user_tasks = user_tasks
        for number, _ in user_tasks.items():
            button = ui.Button(label=f"#{number}", style=ButtonStyle.danger)
            button.callback = lambda interaction, number=number: self.stop_task(
                interaction, number
            )
            self.add_item(button)

    async def stop_task(
        self,
        interaction: Interaction,
        number: int,
    ):
        """停止任務。"""

        self.user_tasks[number].cancel()
        del self.user_tasks[number]

        button = next(
            (
                item
                for item in self.children
                if isinstance(item, ui.Button) and item.label == f"#{number}"
            ),
            None,
        )
        if button:
            button.disabled = True

        await interaction.response.edit_message(
            content=f"成功停止 #{number} 的任務", view=self, delete_after=DELETE_TIME
        )


def _get_or_create_session(user_id: int) -> Session:
    """取得或建立使用者的 session。"""

    if (session := sessions.get(user_id)) is None:
        session = Session()
        sessions[user_id] = session

    return session


def _get_or_create_user_tasks(
    user_id: int,
) -> Dict[int, tasks.Loop[Coroutine[Any, Any, None]]]:
    """取得或建立使用者的 tasks。"""

    if (user_tasks := all_tasks.get(user_id)) is None:
        user_tasks = {}
        all_tasks[user_id] = user_tasks

    return user_tasks


def _is_login(user_id: int) -> str:
    """如果使用者已登入，回傳使用者名稱，否則回傳 None。"""

    user = None
    if session := sessions.get(user_id, None):
        resp = session.get(NINE_GRID_IP, verify=False)
        soup = BeautifulSoup(resp.text, "lxml")
        user = soup.select_one("strong")

    return user.text if user else None


def _logout(user_id: int) -> None:
    """刪除使用者的 session。"""

    if sessions.get(user_id, None):
        del sessions[user_id]


def _login(user_id: int, username: str, password: str) -> None:
    """建立使用者的 session 並登入。"""

    session = _get_or_create_session(user_id)

    resp = session.get(login_url, verify=False)
    soup = BeautifulSoup(resp.text, "lxml")
    authenticity_token = soup.select_one("input[name=authenticity_token]")["value"]
    data = {
        "utf8": "✓",
        "user[username]": username,
        "user[password]": password,
        "authenticity_token": authenticity_token,
    }

    session.post(login_url, data=data, verify=False)


async def _submit_judgement(interaction: Interaction, view: any) -> None:
    """提交批改。"""

    user_id = interaction.user.id
    if not _is_login(user_id):
        await interaction.channel.send(
            "請先登入", view=LoginView(), delete_after=DELETE_TIME
        )
        return

    session = sessions.get(user_id)
    resp = session.post(judge_url, data=view.data, verify=False)

    if resp.status_code == 200:
        view.clear_items()
        await interaction.message.edit(content="成功批改", view=view)
    else:
        await interaction.message.edit(content="批改失敗")

    await interaction.response.defer()


async def _fetch_answers(
    interaction: Interaction,
    number: int,
    limit: int = 3,
    ref: bool = False,
    disable_md: bool = False,
    delete_after: int = DELETE_TIME,
):
    """取得指定問題的繳交答案。

    Parameters
    -----------
    number: int
        輸入問題編號。
    limit: int
        輸入要顯示的回答數量。
    ref: bool
        是否顯示參考答案。
    disable_md: bool
        是否禁用 Markdown。
    delete_after: int
        設定刪除訊息的時間。
    """

    user_id = interaction.user.id
    if not _is_login(user_id):
        if interaction.response.is_done():
            await interaction.channel.send(
                "請先登入", view=LoginView(), delete_after=delete_after
            )
        else:
            await interaction.response.send_message(
                "請先登入", view=LoginView(), delete_after=delete_after
            )

        return

    session = sessions.get(user_id)
    resp = session.get(query_url + str(number), verify=False)
    soup = BeautifulSoup(resp.text, "lxml")

    if answers := soup.select("#main > div > table > tbody > tr"):
        if interaction.response.is_done():
            await interaction.channel.send(
                f"#{number} 有 {len(answers)} 筆繳交答案，顯示前 {min(len(answers),limit)} 筆。"
            )
        else:
            await interaction.response.send_message(
                f"#{number} 有 {len(answers)} 筆繳交答案，顯示前 {min(len(answers),limit)} 筆。"
            )

        if ref:
            resp = session.get(f"{quiz_url}/{number}", verify=False)
            soup = BeautifulSoup(resp.text, "lxml")
            content = soup.select_one(
                "#main > div > h5.ui.attached.orange.header"
            ).find_next_sibling()

            reference_content = (
                f"# Reference:\n```{content.text}```"
                if disable_md
                else f"# Reference:\n{content.text}"
            )
            await interaction.channel.send(reference_content, delete_after=delete_after)

    else:
        if interaction.response.is_done():
            await interaction.channel.send(f"#{number} 沒人繳交答案", silent=True)
        else:
            await interaction.response.send_message(
                f"#{number} 沒人繳交答案", silent=True
            )

        return

    answer_urls = [
        answer.select_one("td:nth-child(5) > a")["href"] for answer in answers
    ][:limit]

    answer_urls = [f"{NINE_GRID_IP}{url}&ans_format=text" for url in answer_urls]
    for answer_url in answer_urls:
        resp = session.get(answer_url, verify=False)
        soup = BeautifulSoup(resp.text, "lxml")
        content = soup.select_one(
            "#main > div > div > h5.ui.orange.top.attached.header"
        ).find_next_sibling()

        csrf_token = soup.select_one("meta[name=csrf-token]")["content"]

        query_params = parse_qs(urlparse(answer_url).query)
        answer_id = query_params.get("target", [None])[0]

        message_content = (
            f"\n\u200b\n>>> ```{content.text.strip(' \n')}```"
            if disable_md
            else f"\n\u200b\n>>> {content.text.strip(' \n')}"
        )
        await interaction.channel.send(
            message_content,
            view=JudgeView(answer_id, csrf_token, delete_after),
            delete_after=delete_after,
        )


@bot.event
async def on_ready():
    """Bot 上線時執行。"""

    logger.info("Bot 已上線")


@bot.command()
@commands.is_owner()
async def sync(ctx: commands.Context):
    """同步指令。"""

    await bot.tree.sync()
    await ctx.message.add_reaction("✅")


@unique
class PAGE(Enum):
    """Nine Grids 頁面。"""

    HOME = auto()
    LOGIN = auto()
    USER = auto()
    CHAPTER = auto()
    QUIZ = auto()
    ANSWER = auto()
    JUDGEMENT = auto()


PAGE_URLS = {
    PAGE.HOME: "",
    PAGE.LOGIN: "/p/users/sign_in",
    PAGE.USER: "/users",
    PAGE.CHAPTER: "/chapters",
    PAGE.QUIZ: "/quizzes",
    PAGE.ANSWER: "/answers",
    PAGE.JUDGEMENT: "/judgements",
}


@bot.tree.command()
async def show_url(interaction: Interaction, page: PAGE = PAGE.HOME):
    """顯示 Nine Grids 的網址。

    Parameters
    -----------
    page: PAGE
        選擇頁面。
    """

    await interaction.response.send_message(NINE_GRID_URL + PAGE_URLS[page])


@bot.tree.command()
async def check_login(interaction: Interaction):
    """確認是否登入。"""

    if user := _is_login(interaction.user.id):
        await interaction.response.send_message(
            f"{user} 已登入！", view=LogoutView(), delete_after=DELETE_TIME
        )
    else:
        await interaction.response.send_message(
            "未登入！", view=LoginView(), delete_after=DELETE_TIME
        )


@bot.tree.command()
async def login(interaction: Interaction, username: str, password: str):
    """登入 Nine Grids。

    Parameters
    -----------
    username: str
        輸入使用者名稱(學號)。
    password: str
        輸入密碼。
    """

    user_id = interaction.user.id
    if _is_login(user_id):
        await interaction.response.send_message(
            "請先登出！", view=LogoutView(), delete_after=DELETE_TIME
        )
        return

    _login(user_id, username, password)

    if user := _is_login(user_id):
        await interaction.response.send_message(f"{user} 登入成功！")
    else:
        await interaction.response.send_message(
            "登入失敗！", view=LoginView("重試"), delete_after=DELETE_TIME
        )


@bot.tree.command()
async def logout(interaction: Interaction):
    """登出 Nine Grids。"""

    user_id = interaction.user.id
    _logout(user_id)

    if user := _is_login(user_id):
        await interaction.response.send_message(f"{user} 登出失敗！")
    else:
        await interaction.response.send_message(
            "登出成功！", view=LoginView("重新登入"), delete_after=DELETE_TIME
        )


@bot.tree.command()
async def fetch_problem(
    interaction: Interaction,
    number: int,
    disable_md: bool = False,
):
    """取得指定問題。

    Parameters
    -----------
    number: int
        輸入問題編號。
    disable_md: bool
        是否禁用 Markdown。
    """

    user_id = interaction.user.id
    if not _is_login(user_id):
        await interaction.response.send_message(
            "請先登入", view=LoginView(), delete_after=DELETE_TIME
        )
        return

    await interaction.response.defer()
    session = sessions.get(user_id)
    resp = session.get(f"{quiz_url}/{str(number)}/edit", verify=False)
    soup = BeautifulSoup(resp.text, "lxml")

    chapter_div = soup.select_one("input[name='quiz[chapter_id]']").find_parent("div")
    chapter = chapter_div.text.strip().split("\n")[-1].strip()
    title = soup.select_one("input#quiz_title")["value"]
    content = soup.select_one("textarea#quiz_content").text
    reference = soup.select_one("textarea#quiz_reference").text

    content = sub(r"!\[", "[", content)
    reference = sub(r"!\[", "[", reference)

    message = (
        f"# No.{number}\n\n"
        f"### Chapter: {chapter}\n"
        f"## Title: {title}\n\n"
        f"## Content:\n{content}\n"
        f"## Reference:\n"
    )
    message += f"```{reference}```\n\u200b" if disable_md else f"{reference}\n\u200b"

    await interaction.followup.send(message)


@bot.tree.command()
async def fetch_answers(
    interaction: Interaction,
    number: int,
    limit: int = 3,
    ref: bool = False,
    disable_md: bool = False,
):
    """取得指定問題的繳交答案。

    Parameters
    -----------
    number: int
        輸入問題編號。
    limit: int
        輸入要顯示的回答數量。
    ref: bool
        是否顯示參考答案。
    """

    await _fetch_answers(interaction, number, limit, ref, disable_md)


@bot.tree.command()
async def set_task(
    interaction: Interaction,
    number: int,
    limit: int = 3,
    ref: bool = False,
    disable_md: bool = False,
    interval: int = 150,
):
    """設定定期取得指定問題的繳交答案的任務。

    Parameters
    -----------
    number: int
        輸入問題編號。
    limit: int
        輸入每次要顯示的回答數量。
    ref: bool
        是否顯示參考答案。
    disable_md: bool
        是否禁用 Markdown。
    interval: int
        輸入取得回答的間隔時間(秒)。
    """

    user_id = interaction.user.id
    if not _is_login(user_id):
        await interaction.response.send_message(
            "請先登入", view=LoginView(), delete_after=DELETE_TIME
        )
        return

    @tasks.loop(seconds=interval)
    async def repeated_task():
        await _fetch_answers(interaction, number, limit, ref, disable_md, interval)

    user_tasks = _get_or_create_user_tasks(user_id)
    exist = number in user_tasks

    if exist:
        user_tasks[number].cancel()
        del user_tasks[number]
        await interaction.response.send_message(
            f"已重新設定每 {interval} 秒取得一次 #{number} 回答的任務"
        )
    else:
        await interaction.response.send_message(
            f"已設定每 {interval} 秒取得一次 #{number} 回答的任務"
        )

    user_tasks[number] = repeated_task
    user_tasks[number].start()


@bot.tree.command()
async def stop_task(interaction: Interaction, number: int = None):
    """停止定期取得指定問題的繳交答案的任務

    Parameters
    -----------
    number: int
        輸入問題編號。
    """

    user_id = interaction.user.id
    if not _is_login(user_id):
        await interaction.response.send_message(
            "請先登入", view=LoginView(), delete_after=DELETE_TIME
        )
        return

    user_tasks = _get_or_create_user_tasks(user_id)
    if number is None:
        if user_tasks:
            await interaction.response.send_message(
                "請選擇要停止的任務",
                view=StopTaskView(user_tasks),
                delete_after=DELETE_TIME,
            )
        else:
            await interaction.response.send_message(
                "沒有任務可以停止", delete_after=DELETE_TIME
            )
    else:
        if number in user_tasks:
            user_tasks[number].cancel()
            del user_tasks[number]
            await interaction.response.send_message(f"已停止 #{number} 的任務")
        else:
            await interaction.response.send_message(f"沒有 #{number} 的任務")


if __name__ == "__main__":
    bot.run(os.getenv("DISCORD_TOKEN"), log_handler=handler)
