from bot.common import router as common_router
from bot.deadlines import router as deadlines_router
from bot.teachers import router as teachers_router
from bot.profile import router as profile_router



all_handlers_routers = [
    common_router,
    deadlines_router,
    teachers_router,
    profile_router,

]