# backend/app/core/security.py

# from fastapi import Depends, Request
# from fastapi_users import BaseUserManager, FastAPIUsers, UUIDIDMixin
# from fastapi_users.authentication import (
#     AuthenticationBackend,
#     BearerTransport,
#     CookieTransport,
#     JWTStrategy, # Already here, but verify it's from 'authentication'
# )
# from fastapi_users_db_sqlalchemy import SQLAlchemyUserDatabase # Import from the adapter package
# from fastapi_users import exceptions # Import exceptions for user management
# from fastapi_users.password import get_password_hash # Import get_password_hash for hashing
# from fastapi_users.password import PasswordHelper # Import PasswordHelper

# from app.db.models.user import User # Your SQLAlchemy User model
# from app.db.session import get_user_db # Your dependency to get user DB adapter

# # --- Password Hashing ---
# # Create an instance of PasswordHelper.
# # You can customize schemes and deprecated schemes if needed.
# # Default: ["bcrypt"], deprecated="auto"
# password_helper = PasswordHelper()


# # --- User Manager ---
# class UserManager(UUIDIDMixin, BaseUserManager[User, uuid.UUID]):
#     reset_password_token_secret = settings.SECRET_KEY # Use main secret or a specific one
#     verification_token_secret = settings.SECRET_KEY # Use main secret or a specific one

#     async def on_after_register(self, user: User, request: Request | None = None) -> None:
#         # Note: Added 'request: Request | None = None' to match superclass signature
#         print(f"User {user.id} with email {user.email} has registered.")
#         # Add any post-registration logic here (e.g., sending welcome email)

#     async def on_after_forgot_password(
#         self, user: User, token: str, request: Request | None = None
#     ) -> None:
#         # Note: Added 'request: Request | None = None'
#         print(f"User {user.id} has requested a password reset. Token: {token}")
#         # Add logic to send password reset email with token

#     async def on_after_request_verify(
#         self, user: User, token: str, request: Request | None = None
#     ) -> None:
#         # Note: Added 'request: Request | None = None'
#         print(f"Verification requested for user {user.id}. Token: {token}")
#         # Add logic to send verification email with token

#     async def create(
#         self,
#         user_create: "schemas.UC", # Use the generic type hint from BaseUserManager
#         safe: bool = False,
#         request: Request | None = None,
#     ) -> User:
#         """
#         Override create to ensure role and is_superuser are handled if passed.
#         `fastapi-users` UserCreate schema might not have `role`.
#         Your custom UserCreate schema in `app.schemas.user.UserCreate` does.
#         """
#         await self.validate_password(user_create.password, user_create)

#         existing_user_by_email = await self.get_by_email(user_create.email)
#         if existing_user_by_email is not None:
#             raise exceptions.UserAlreadyExists() # Import exceptions from fastapi_users

#         user_dict = (
#             user_create.create_update_dict()
#             if safe
#             else user_create.create_update_dict_superuser()
#         )
#         password = user_dict.pop("password")
#         user_dict["hashed_password"] = self.hash_password(password) # Use the instance's hash_password

#         # Handle custom 'role' and ensure 'is_superuser' consistency
#         # This assumes your UserCreate schema (`app.schemas.user.UserCreate`) has 'role'
#         if "role" in user_dict:
#             # If role is 'admin', ensure is_superuser is True
#             if user_dict["role"] == "admin":
#                 user_dict["is_superuser"] = True
#             # If role is 'standard', ensure is_superuser is False
#             elif user_dict["role"] == "standard":
#                 user_dict["is_superuser"] = False
#         elif "is_superuser" in user_dict and user_dict["is_superuser"] is True:
#             # If only is_superuser is True, set role to 'admin'
#             user_dict["role"] = "admin"


#         created_user = await self.user_db.create(user_dict)

#         await self.on_after_register(created_user, request)

#         return created_user

#     async def hash_password(self, password: str) -> str:
#         """
#         Ensure this method uses the `password_helper` instance.
#         This overrides the method in BaseUserManager to ensure our helper is used.
#         """
#         return password_helper.hash(password)


# async def get_user_manager(user_db: SQLAlchemyUserDatabase = Depends(get_user_db)):
#     """Dependency to get the UserManager instance."""
#     # Pass the password_helper instance to the UserManager
#     yield UserManager(user_db, password_helper=password_helper)


# # --- JWT Strategy (Unified for Access & Refresh Tokens handled by auth_backend) ---
# def get_jwt_strategy() -> JWTStrategy:
#     """
#     Returns the JWT strategy.
#     This strategy is used by the auth_backend to generate tokens.
#     The lifetime for access tokens is `lifetime_seconds`.
#     The lifetime for refresh tokens generated by this strategy (if done explicitly)
#     would be `refresh_lifetime_seconds`. However, when `auth_backend.login()` uses
#     `CookieTransport`, the cookie's `max_age` typically dictates the refresh token's validity.
#     """
#     return JWTStrategy(
#         secret=settings.SECRET_KEY, # Main secret for tokens generated by this strategy
#         lifetime_seconds=settings.ACCESS_TOKEN_EXPIRE_MINUTES * 60,
#         # refresh_lifetime_seconds can be set if you plan to use strategy.write_token()
#         # for refresh tokens with a different lifetime than the cookie max_age.
#         # For simplicity with auth_backend and CookieTransport, this is often omitted,
#         # as the cookie's own max_age serves as the effective refresh token lifetime.
#         # If you DO set it, make sure it aligns with your refresh token concept.
#         # For example:
#         # refresh_lifetime_seconds=settings.REFRESH_TOKEN_EXPIRE_DAYS * 24 * 60 * 60,
#         algorithm=settings.ALGORITHM,
#     )


# # --- Authentication Transports ---
# # BearerTransport is for reading access tokens from the Authorization header.
# bearer_transport = BearerTransport(tokenUrl=f"{settings.API_V1_STR}/auth/login")

# # CookieTransport is for setting/reading the refresh token cookie.
# cookie_transport = CookieTransport(
#     cookie_name=settings.REFRESH_TOKEN_COOKIE_NAME,
#     cookie_max_age=settings.REFRESH_TOKEN_EXPIRE_DAYS * 24 * 60 * 60, # This is the refresh token lifetime
#     cookie_path=f"{settings.API_V1_STR}/auth", # Scope cookie to auth paths
#     cookie_secure=settings.COOKIE_SECURE,
#     cookie_httponly=True, # Crucial for security
#     cookie_samesite=settings.COOKIE_SAMESITE, # "lax" or "strict"
# )


# # --- Authentication Backend Instance ---
# # This backend will be used for the main fastapi_users routers (login, logout, etc.)
# # and can also be used in your custom endpoints.
# # When login occurs via this backend with CookieTransport, it sets the refresh token cookie.
# # The access token is typically returned in the response body by default.
# auth_backend = AuthenticationBackend(
#     name="jwt",
#     transport=cookie_transport, # This transport is used for login response (setting cookie)
#                                 # For verifying requests, it will also check this cookie if no Bearer token.
#                                 # To enforce Bearer for access, BearerTransport is also needed.
#                                 # Actually, FastAPIUsers can use multiple transports for verification.
#                                 # The `transport` param here is for the *login response*.
#     get_strategy=get_jwt_strategy,
# )

# # --- FastAPIUsers Main Instance ---
# # Pass *all* authentication backends you want to use.
# # If you want to support both Bearer token for access and Cookie for refresh:
# # The `AuthenticationBackend`'s `transport` parameter is primarily for how it handles login/logout responses.
# # For authenticating incoming requests, FastAPIUsers checks all backends.
# #
# # To clarify:
# # - BearerTransport: Reads "Authorization: Bearer <token>"
# # - CookieTransport: Reads cookie "subRefreshToken"
# #
# # We need an auth_backend that uses CookieTransport for login/logout (to set the refresh cookie)
# # and potentially another for Bearer (or the same one if configured broadly).
# # Let's stick with one `auth_backend` and ensure it works with your custom login.
# # Your custom login uses `auth_backend.login()` which uses `cookie_transport` to set the cookie.
# # The access token you return in the body will be used by the client as a Bearer token.
# # The `current_active_user` dependency will check available auth methods.

# # For request authentication, FastAPIUsers will iterate through the backends.
# # `fastapi_users.current_user()` will try to authenticate using any of the methods
# # associated with the backends passed to `FastAPIUsers([...])`.
# #
# # So, if `auth_backend` is configured with `cookie_transport` as its primary transport,
# # but `bearer_transport` is also "known" to `fastapi_users` through another backend or
# # implicitly, it can get complex.
# #
# # The simplest way with your custom login:
# # 1. `auth_backend` (using `cookie_transport`) handles the refresh token cookie part of login.
# # 2. Your custom login endpoint returns the access token in the body.
# # 3. `current_active_user` needs to be able to validate that Bearer token.
# #
# # This means `fastapi_users` needs to be aware of the Bearer token mechanism for validating
# # incoming requests.

# # Let's define two backends for clarity, one for each transport mechanism,
# # though only one might be used for login response by default.

# # Backend for handling cookie-based refresh token and authentication if no Bearer token
# cookie_auth_backend = AuthenticationBackend(
#     name="jwt-cookie",
#     transport=cookie_transport,
#     get_strategy=get_jwt_strategy,
# )

# # Backend for handling Bearer token based access token authentication
# bearer_auth_backend = AuthenticationBackend(
#     name="jwt-bearer",
#     transport=bearer_transport,
#     get_strategy=get_jwt_strategy,
# )

# fastapi_users = FastAPIUsers[User, uuid.UUID](
#     get_user_manager,
#     [cookie_auth_backend, bearer_auth_backend], # Provide both backends
# )

# # Your custom login endpoint in `app/api/routers/auth.py` should use `cookie_auth_backend.login()`
# # to set the cookie, and then you manually return the access token in the response body.
# # Example:
# #   `access_token = await get_jwt_strategy().write_token({"sub": str(user.id), ...})`
# #   `response = await cookie_auth_backend.login(strategy_access_token_obj_not_string, user)`
# #   `response.body = {"access_token": access_token, "token_type": "bearer"}`

# # Actually, the `auth_backend.login()` method itself takes the `strategy_response` (which is the access token object)
# # and the user, and its job is to use its configured transport to "log the user in".
# # If `auth_backend`'s transport is `cookie_transport`, it sets the cookie.
# # The `strategy_response` (AccessToken object) from `auth_backend.login()` is what you should return if you want the access token in the body.

# # So, one `auth_backend` with `cookie_transport` is fine for your custom login.
# # `fastapi_users` will still use `bearer_auth_backend` to validate incoming bearer tokens.

# # Corrected `fastapi_users` instance:
# # The main `auth_backend` used for routers will be the first one that supports login.
# # Your custom login overrides this anyway.
# # The list of auth_methods is what `current_user` uses.

# # --- Reusable Dependencies for route protection ---
# # These will try all authentication methods provided in `fastapi_users` instance.
# current_active_user = fastapi_users.current_user(active=True)
# current_active_superuser = fastapi_users.current_user(active=True, superuser=True)
# current_user_optional = fastapi_users.current_user(optional=True) # useful for optional authentication
# current_active_verified_user = fastapi_users.current_user(active=True, verified=True)
# current_active_verified_superuser = fastapi_users.current_user(active=True, verified=True, superuser=True)
