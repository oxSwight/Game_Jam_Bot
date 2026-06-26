from aiogram.fsm.state import State, StatesGroup


class RegistrationStates(StatesGroup):
    consent = State()
    nickname = State()
    email = State()
    main_category = State()
    blueprint_subcategory = State()
    skill_category = State()
    subcategories = State()
    experience = State()
    tools = State()
    tools_other = State()
    motivation = State()
    confirm = State()
