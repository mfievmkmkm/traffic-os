import os
from openai import AsyncOpenAI

KEY = os.getenv('LLM_API_KEY', '')
BASE_URL = os.getenv('LLM_BASE_URL', 'https://polza.ai/api/v1')
MODEL = os.getenv('LLM_MODEL', 'deepseek/deepseek-v4-flash')

client = AsyncOpenAI(api_key=KEY, base_url=BASE_URL) if KEY else None

async def reply_suggestion(context, inbound):
    if not client:
        return 'AI выключен: добавь LLM_API_KEY в Railway.'

    prompt = f'''Ты помощник оператора Telegram CRM. Предложи 3 коротких естественных ответа на входящее сообщение.
Правила: не выдумывай факты; не дави; не маскируй рекламу; не обещай доходность; не проси продолжать после отказа; не используй чувствительные характеристики человека для таргетинга. Если человек отказался — вежливо заверши диалог. Если спрашивает о рисках трейдинга — не преуменьшай их.
Контекст лида: {context or 'нет'}
Входящее сообщение: {inbound}
Ответ только на русском. Ровно 3 варианта, каждый с новой строки.'''

    try:
        r = await client.chat.completions.create(
            model=MODEL,
            messages=[{'role': 'user', 'content': prompt}],
            temperature=0.7,
            max_tokens=700,
        )
        return (r.choices[0].message.content or '').strip()
    except Exception as e:
        return f'AI временно недоступен: {type(e).__name__}. Проверь LLM_API_KEY, баланс Polza и LLM_MODEL.'


async def outreach_hooks(context, source='Telegram'):
    """Create three context-based, permission-first opening messages."""
    if not client:
        return 'AI выключен: добавь LLM_API_KEY в Railway.'

    prompt = f'''Ты пишешь первые сообщения для оператора Telegram CRM.
Нужны РОВНО 3 коротких варианта первого сообщения потенциальному лиду на русском.

Контекст сообщения/интереса человека: {context or 'нет'}
Источник: {source or 'Telegram'}

Цель: начать естественный разговор и только после интереса предложить релевантный Telegram-канал про крипторынок/трейдинг.

Требования:
- каждый вариант 1-3 коротких предложения;
- цепляйся только за реально данный контекст, ничего не выдумывай;
- не обещай прибыль, сигналы, инсайд, гарантированный заработок;
- без фальшивой срочности, давления и манипуляций;
- не делай вид, что вы знакомы;
- не используй чувствительные характеристики человека;
- не отправляй ссылку сразу: сначала спроси, актуально ли/можно ли скинуть;
- стиль живой, разговорный, без канцелярита и без ощущения AI;
- варианты должны отличаться: 1) контекстный вопрос, 2) любопытство/ценность, 3) максимально прямой.

Верни только 3 готовых сообщения, каждое с новой строки и с префиксами A), B), C).'''

    try:
        r = await client.chat.completions.create(
            model=MODEL,
            messages=[{'role': 'user', 'content': prompt}],
            temperature=0.85,
            max_tokens=650,
        )
        return (r.choices[0].message.content or '').strip()
    except Exception as e:
        return f'AI временно недоступен: {type(e).__name__}. Проверь LLM_API_KEY, баланс Polza и LLM_MODEL.'
