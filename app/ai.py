import os
from openai import AsyncOpenAI

KEY = os.getenv('OPENAI_API_KEY', '')
MODEL = os.getenv('OPENAI_MODEL', 'gpt-5.6-luna')
client = AsyncOpenAI(api_key=KEY) if KEY else None

async def reply_suggestion(context, inbound):
    if not client:
        return 'AI выключен: добавь OPENAI_API_KEY в Railway.'
    prompt = f'''Ты помощник оператора Telegram CRM. Предложи 3 коротких естественных ответа на входящее сообщение.
Правила: не выдумывай факты; не дави; не маскируй рекламу; не обещай доходность; не проси продолжать после отказа; не используй чувствительные характеристики человека для таргетинга. Если человек отказался — вежливо заверши диалог. Если спрашивает о рисках трейдинга — не преуменьшай их.
Контекст лида: {context or 'нет'}
Входящее сообщение: {inbound}
Ответ только на русском. Ровно 3 варианта, каждый с новой строки.'''
    r = await client.responses.create(model=MODEL, input=prompt, store=False)
    return r.output_text.strip()
