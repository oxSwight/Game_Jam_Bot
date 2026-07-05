from aiogram.fsm.state import State, StatesGroup


class AdminStates(StatesGroup):
    reject_reason = State()      # waiting for the free-text rejection reason
    broadcast_message = State()  # waiting for the broadcast body
    broadcast_confirm = State()  # waiting for confirmation of the broadcast


class EditStates(StatesGroup):
    field = State()    # choosing which field to edit
    nickname = State()
    email = State()
