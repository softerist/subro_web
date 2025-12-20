# backend/app/db/base.py

# Import the Base class which all models inherit from.

# Import all SQLAlchemy models defined in your application.
# This is crucial for Alembic's autogenerate feature to discover the models
# and compare them against the current database schema.

# When you add a new model (e.g., a new table), you must import it here.
# The 'noqa' comment can be used to silence linters about unused imports,
# as these imports are indeed used by SQLAlchemy's declarative system implicitly.


# Import all SQLAlchemy models defined in your application.
# This is crucial for Alembic's autogenerate feature to discover the models
# and compare them against the current database schema.
from app.db.base_class import Base  # noqa: F401
from app.db.models.dashboard import DashboardTile  # noqa: F401
from app.db.models.job import Job  # noqa: F401
from app.db.models.storage_path import StoragePath  # noqa: F401
from app.db.models.user import User  # noqa: F401
# Example for future models:
# from app.db.models.another_model import AnotherModel
# from app.db.models.yet_another_model import YetAnotherModel

# Note: The `Base` object itself doesn't need to be re-exported from here
# unless other parts of your application specifically expect to import it
# from `app.db.base`. Typically, models import `Base` from `app.db.base_class`.
# Alembic's env.py will import `Base` from here to access `Base.metadata`.
