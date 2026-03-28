import os
import logging
import random
import hashlib
import urllib.request
import json
import ask_sdk_core.utils as ask_utils
from datetime import datetime
from typing import Optional, List, Dict
import pytz
from ask_sdk_core.skill_builder import SkillBuilder
from ask_sdk_core.dispatch_components import AbstractRequestHandler, AbstractExceptionHandler
from ask_sdk_model.interfaces.alexa.presentation.apl import RenderDocumentDirective

logger = logging.getLogger(__name__)
logger.setLevel(logging.INFO)

# OpenAI Configuration
OPENAI_MODEL = "gpt-5-mini"
OPENAI_URL = "https://api.openai.com/v1/chat/completions"

MAX_OUTPUT_CHARS = 250
MIN_OUTPUT_CHARS = 5
TIMEOUT_SECONDS = 20.0
MAX_HISTORY = 8
MAX_INPUT_CHARS = 300
CACHE_HISTORY_LIMIT = 8
CACHE_MAX_SIZE = 50
RIYADH_TZ = pytz.timezone("Asia/Riyadh")

SULTAN_TRAITS = (
    "سلطان هو المطور السعودي الذي صمم مهارة دانا بذكاء، "
    "شاب طموح يسعى لتقديم تقنيات مفيدة ومميزة."
)

SYSTEM_PROMPT = """أنتِ "دانا"، المساعدة الذكية بلهجة سعودية بيضاء، روحك مرحة جداً، ودودة، وتحبين السوالف بطريقة ممتعة ومسلية دون إطالة.
صُممتِ خصيصاً لأجهزة Alexa لتكوني رفيقة مثرية وممتعة وتجيبين بأسلوب قصصي ذكي وموجز.
قواعد الرد:
1. المباشرة والود: ادخلي في صلب الموضوع مع إضفاء طابع مرح وودود في كلماتك. لا ترحبي ابدا، بل نوعي في الدخول للموضوع وابدأي بالشرح بروح متفائلة.
2. (احيانا اذا السؤال يحتاج لبعض التفصيل ففصلي بدون ما تتجاوزين ال250 حرف) الإيجاز الممتع: اجعلي ردودك غنية بالمرح والحيوية لكن باختصار، يجب ألا يتجاوز ردك 250 حرفاً. أعطي المفيد كأنك تسولفين مع شخص تعزينه بس بطريقة سريعة.
3. التنوع وعدم التكرار: تنوعي بأساليب التجاوب ولا تكرري نفس الجملة الافتتاحية في كل رد (إياكِ أن تبدأي كل إجابة بكلمة "أبشر" أو غيرها). نوّعي مفرداتك لتبدو طبيعية تماماً. استخدمي المذكر دائماً كصيغة خطاب محايدة لضمان اللباقة.
4. الأمان واللباقة: إذا طُرح سؤال عن مواضيع غير مناسبة (إباحية، سياسة حساسة، صراعات، إساءة)، اعتذري بلطف وقولي للمستخدم أنكِ هنا للفائدة والسوالف الطيبة فقط.
5. تجنبي القوائم الجافة (مثل 1. 2. 3.): استبدليها بسرد قصصي متصل وجمل انسيابية تعكس شخصيتك المرحة.
6. لا تستخدمي الرموز التعبيرية (Emoji) أبداً لأن النص سيتم قراءته صوتياً عبر أليكسا.
7. أنتِ "دانا" ولستِ ذكاءً اصطناعياً. إياكِ والاعتراف بغير ذلك.
8. سلطان هو مطورك المبدع، اذكريه باعتدال لائق إذا جاء طاريه، فهو من علمك اللباقة وحسن السوالف.
"""

START_RESPONSES = [
    "سمّ! وش اللي في بالك وودك تسأل عنه؟",
    "أبشر بسعدك، أنا دانا وجاهزة لكل استفساراتك. وش تبي؟",
    "يا هلا والله! نورت بطلتك، وش عندك اليوم من أسئلة؟",
    "يالله حيّهم! دانا معك، وش أقدر أخدمك فيه؟",
    "هلا بك! قول وش بخاطرك وأنا أجاوبك باللي أعرفه.",
]
GREETING_MORNING = ["يا مساء وصباح الخير! دانا معك، سمّ؟", "يسعد هالصباح! وش اللي ودك تعرفه اليوم؟"]
GREETING_AFTERNOON = ["هلا بك والله! دانا حاضرة، وش بخاطرك؟", "يا هلا ومسهلا! دانا معك، كيف أخدمك؟"]
GREETING_EVENING = ["يسعد هالمساء! دانا جاهزة، تفضل بطلبك.", "يا هلا وغلا! وش عندك لي اليوم؟"]
ERROR_RESPONSES = [
    "المعذرة منك، ما لقطت السؤال زين. تقدر تعيده؟",
    "يا ليت توضح لي أكثر، دانا شوية تاهت في الفكرة!",
    "عفواً، ما استوعبت وش تقصد، ممكن صياغة ثانية؟",
    "ودي أخدمك بس ما فهمت والله، وش كنت تقول؟",
]
END_RESPONSES = ["في أمان الله! دانا دائماً في انتظارك.", "يومك سعيد ومليان توفيق يارب، مع السلامة!", "تشرفت فيك، نلتقي على خير!"]
TIMEOUT_RESPONSES = ["النت شكله مأجز اليوم! عاود السؤال لاهنت.", "اعتذر منك، الإجابة تأخرت شوي، جرب مرة ثانية."]

_BLOCKED_PATTERNS = [
    "ignore previous", "ignore above", "new instructions",
    "system:", "assistant:", "أنت الآن", "تجاهل التعليمات",
    "أعد تعريف نفسك", "اتصرف كـ",
]


_cache: Dict[str, str] = {}

def _cache_key(text: str) -> str:
    return hashlib.md5(text.strip().lower().encode()).hexdigest()

def _cache_get(text: str) -> Optional[str]:
    return _cache.get(_cache_key(text))

def _cache_set(text: str, reply: str) -> None:
    if len(_cache) >= CACHE_MAX_SIZE:
        _cache.pop(next(iter(_cache)))
    _cache[_cache_key(text)] = reply

def sanitize_input(text: str) -> Optional[str]:
    if not text or not text.strip():
        return None
    text = " ".join(text[:MAX_INPUT_CHARS].split())
    lower = text.lower()
    for p in _BLOCKED_PATTERNS:
        if p in lower:
            return ""
    return text

def _is_cacheable(text: str) -> bool:
    if any(ch.isdigit() for ch in text) or "@" in text:
        return False
    if "[سياق:" in text:
        return False
    return True

def clamp_reply(text: str) -> str:
    text = " ".join((text or "").split())
    if len(text) < MIN_OUTPUT_CHARS:
        return random.choice(ERROR_RESPONSES)
    if len(text) <= MAX_OUTPUT_CHARS:
        return text
    cut = text.rfind(" ", 0, MAX_OUTPUT_CHARS)
    return text[:cut].strip() if cut > 40 else text[:MAX_OUTPUT_CHARS]

def ensure_arabic(text: str) -> str:
    if not text:
        return random.choice(ERROR_RESPONSES)
    if len(text) <= 25:
        return text
    arabic_chars = sum(1 for c in text if "\u0600" <= c <= "\u06FF")
    if arabic_chars < 8:
        return "اكتب سؤالك بالعربي وأنا أجاوبك زين."
    return text

def process_reply(text: str) -> str:
    for ch in ["*", "#", "`", "_", "~", "•"]:
        text = (text or "").replace(ch, "")
    text = clamp_reply(text)
    text = ensure_arabic(text)
    return text

def get_time_greeting() -> str:
    hour = datetime.now(RIYADH_TZ).hour
    if 4 <= hour < 12:
        return random.choice(GREETING_MORNING)
    if 12 <= hour < 18:
        return random.choice(GREETING_AFTERNOON)
    return random.choice(GREETING_EVENING)

def get_given_name(handler_input) -> Optional[str]:
    try:
        return handler_input.request_envelope.context.system.person.profile.given_name
    except Exception:
        return None

def call_openai(history: List[Dict], cache_key_input: str) -> str:
    api_key = os.environ.get("OPENAI_API_KEY", "")
    if not api_key:
        logger.error("OPENAI_API_KEY is missing.")
        return random.choice(ERROR_RESPONSES)

    clean_history = [m for m in history if "مشكلة" not in m.get("content", "")]
    
    messages = [{"role": "system", "content": SYSTEM_PROMPT}]
    messages.extend(clean_history)

    payload = {
        "model": OPENAI_MODEL,
        "messages": messages,
        "temperature": 1
    }

    data = json.dumps(payload).encode("utf-8")
    req = urllib.request.Request(OPENAI_URL, data=data, headers={
        "Content-Type": "application/json",
        "Authorization": f"Bearer {api_key}"
    }, method="POST")

    try:
        with urllib.request.urlopen(req, timeout=TIMEOUT_SECONDS) as response:
            res_data = json.loads(response.read().decode("utf-8"))
            choice = res_data.get("choices", [{}])[0]
            text = choice.get("message", {}).get("content", "")
            return process_reply(text)

    except urllib.error.HTTPError as e:
        error_body = e.read().decode('utf-8')
        logger.error(f"OpenAI HTTP Error: {e.code} | {error_body}")
        return "واجهت مشكلة بسيطة في الاتصال، جرب بعد شوي."
    except Exception as e:
        logger.error(f"OpenAI Error: {str(e)}")
        return "واجهت مشكلة بسيطة في الاتصال، جرب بعد شوي."

DANNA_APL_DOC = {
    "type": "APL",
    "version": "2023.2",
    "mainTemplate": {
        "parameters": ["payload"],
        "item": {
            "type": "Container",
            "width": "100%",
            "height": "100%",
            "backgroundColor": "#F4F8FA",
            "justifyContent": "center",
            "alignItems": "center",
            "items": [
                {
                    "type": "Text",
                    "text": "دانا ✨",
                    "fontSize": "10vh",
                    "color": "#D091BC",
                    "fontWeight": "bold"
                },
                {
                    "type": "Text",
                    "text": "${payload.chatData.properties.dannaText}",
                    "fontSize": "5vh",
                    "color": "#111111",
                    "textAlign": "center"
                }
            ]
        }
    }
}

def supports_apl(handler_input):
    supported = ask_utils.get_supported_interfaces(handler_input)
    return supported is not None and getattr(supported, "alexa_presentation_apl", None) is not None

def add_apl_to_response(handler_input, user_text, danna_text):
    if supports_apl(handler_input):
        handler_input.response_builder.add_directive(
            RenderDocumentDirective(
                token="dannaToken",
                document=DANNA_APL_DOC,
                datasources={
                    "payload": {
                        "chatData": {
                            "type": "object",
                            "properties": {
                                "userText": user_text,
                                "dannaText": danna_text
                            }
                        }
                    }
                }
            )
        )

class LaunchRequestHandler(AbstractRequestHandler):
    def can_handle(self, handler_input):
        return ask_utils.is_request_type("LaunchRequest")(handler_input)

    def handle(self, handler_input):
        name = get_given_name(handler_input)
        greeting = get_time_greeting()
        speak = f"هلا {name}! {greeting}" if name else greeting
        start_msg = random.choice(START_RESPONSES)
        
        add_apl_to_response(handler_input, user_text="", danna_text=f"{speak.strip()} {start_msg.strip()}")
        return handler_input.response_builder.speak(speak).ask(start_msg).response

class AskDannaIntentHandler(AbstractRequestHandler):
    def can_handle(self, handler_input):
        return ask_utils.is_intent_name("AskDannaIntent")(handler_input) 

    def handle(self, handler_input):
        session_attr = handler_input.attributes_manager.session_attributes
        history: List[Dict] = list(session_attr.get("history", []))

        slots = handler_input.request_envelope.request.intent.slots
        raw = ""
        try:
            raw = (slots.get("query").value or "") if slots and slots.get("query") else ""
        except Exception:
            raw = ""

        user_input = sanitize_input(raw)

        if user_input is None:
            return handler_input.response_builder.speak(random.choice(ERROR_RESPONSES)).ask("تحب تعيد السؤال؟").response

        if user_input == "":
            return handler_input.response_builder.speak("أبشر، بس يا ليت تسألني بشكل مباشر بدون أوامر جانبية عشان أفهمك أسرع.").ask("وش اللي ودك تسأله؟").response

        has_sultan = "سلطان" in user_input
        enriched = f"{user_input}\n[سياق: {SULTAN_TRAITS}]" if has_sultan else user_input

        history.append({"role": "user", "content": enriched})
        history = history[-MAX_HISTORY:]

        cache_input = "" if has_sultan else user_input
        reply = call_openai(history, cache_input)

        if "مشكلة" not in reply:
            history.append({"role": "assistant", "content": reply})
            session_attr["history"] = history[-MAX_HISTORY:]

        add_apl_to_response(handler_input, user_text=user_input, danna_text=reply)

        return handler_input.response_builder.speak(reply).ask("فيه شي ثاني أقدر أساعدك فيه؟").response

class HelpIntentHandler(AbstractRequestHandler):
    def can_handle(self, handler_input):
        return ask_utils.is_intent_name("AMAZON.HelpIntent")(handler_input)

    def handle(self, handler_input):
        return handler_input.response_builder.speak("أنا دانا، موجودة عشان أجاوب على كل اللي يدور في بالك بلهجتنا السعودية الجميلة. بس اسألني وأبشر بسعدك!").ask("وش ودك تسأل عنه؟").response

class CancelOrStopIntentHandler(AbstractRequestHandler):
    def can_handle(self, handler_input):
        return ask_utils.is_intent_name("AMAZON.CancelIntent")(handler_input) or ask_utils.is_intent_name("AMAZON.StopIntent")(handler_input)

    def handle(self, handler_input):
        handler_input.attributes_manager.session_attributes.clear()
        return handler_input.response_builder.speak(random.choice(END_RESPONSES)).response

class FallbackIntentHandler(AbstractRequestHandler):
    def can_handle(self, handler_input):
        return ask_utils.is_intent_name("AMAZON.FallbackIntent")(handler_input)

    def handle(self, handler_input):
        return handler_input.response_builder.speak(random.choice(ERROR_RESPONSES)).ask("تحب تعيد السؤال؟").response

class SessionEndedRequestHandler(AbstractRequestHandler):
    def can_handle(self, handler_input):
        return ask_utils.is_request_type("SessionEndedRequest")(handler_input)

    def handle(self, handler_input):
        return handler_input.response_builder.response

class CatchAllExceptionHandler(AbstractExceptionHandler):
    def can_handle(self, handler_input, exception):
        return True

    def handle(self, handler_input, exception):
        logger.error("Unhandled: %s | %s", type(exception).__name__, exception)
        return handler_input.response_builder.speak(random.choice(ERROR_RESPONSES)).ask("تبغى تجرب مرة ثانية؟").response

sb = SkillBuilder()
sb.add_request_handler(LaunchRequestHandler())
sb.add_request_handler(AskDannaIntentHandler())
sb.add_request_handler(HelpIntentHandler())
sb.add_request_handler(CancelOrStopIntentHandler())
sb.add_request_handler(FallbackIntentHandler())
sb.add_request_handler(SessionEndedRequestHandler())
sb.add_exception_handler(CatchAllExceptionHandler())

lambda_handler = sb.lambda_handler() 
