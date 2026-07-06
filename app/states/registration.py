from aiogram.fsm.state import State, StatesGroup


class RegistrationStates(StatesGroup):
    captcha = State()       # anti-bot emoji gate, before anything else
    consent = State()
    nickname = State()
    email = State()
    category = State()      # tier 1: parent category (Programming, 3D Art, ...)
    roles = State()         # tier 2: concrete role(s) within the category
    experience = State()
    engine = State()
    engine_other = State()
    tools = State()
    tools_other = State()
    motivation = State()
    confirm = State()
