from aiogram.fsm.state import State, StatesGroup


class CreatePost(StatesGroup):
    waiting_for_content = State()
    waiting_for_channel = State()
    waiting_for_confirmation = State()
    waiting_for_schedule_time = State()
