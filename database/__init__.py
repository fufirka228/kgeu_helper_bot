from database.db_students import init_db, get_student, add_student
from database.db_deadlines import (
    get_group_deadlines,
    get_student_completed_ids,
    toggle_deadline_status,
    add_deadline,
)