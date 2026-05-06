"""
Authentication module for QuantGen API.
Provides JWT token generation, verification, and password hashing.
"""

import secrets
from datetime import datetime, timedelta
from typing import Optional, Dict, Any

# Configure logging
import logging
logger = logging.getLogger(__name__)

# Try to import optional dependencies
try:
    from jose import jwt, JWTError
    JWT_AVAILABLE = True
except ImportError:
    JWT_AVAILABLE = False
    logger.warning("python-jose not available. JWT features will be disabled.")

try:
    from passlib.context import CryptContext
    PASSLIB_AVAILABLE = True
except ImportError:
    PASSLIB_AVAILABLE = False
    logger.warning("passlib not available. Password hashing will be disabled.")

# Configuration
SECRET_KEY = secrets.token_urlsafe(32)
ALGORITHM = "HS256"
ACCESS_TOKEN_EXPIRE_MINUTES = 60 * 24  # 24 hours
REFRESH_TOKEN_EXPIRE_DAYS = 7

# Password hashing context
pwd_context = None
if PASSLIB_AVAILABLE:
    pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")  # type: ignore[possibly-unbound]


def verify_password(plain_password: str, hashed_password: str) -> bool:
    """Verify a password against its hash."""
    if pwd_context is None:
        return False
    try:
        return pwd_context.verify(plain_password, hashed_password)
    except (ValueError, TypeError) as e:
        logger.error("Password verification failed: %s", e)
        return False


def get_password_hash(password: str) -> str:
    """Hash a password."""
    if pwd_context is None:
        raise ValueError("Password hashing not available")
    try:
        return pwd_context.hash(password)
    except Exception as e:  # pylint: disable=broad-exception-caught
        logger.error("Password hashing failed: %s", e)
        raise ValueError("Failed to hash password") from e


def create_access_token(data: Dict[str, Any], expires_delta: Optional[timedelta] = None) -> str:
    """Create a new access token."""
    if not JWT_AVAILABLE:
        raise ValueError("JWT not available")
    to_encode = data.copy()

    if expires_delta:
        expire = datetime.utcnow() + expires_delta
    else:
        expire = datetime.utcnow() + timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES)

    to_encode.update({
        "exp": expire,
        "iat": datetime.utcnow(),
        "type": "access"
    })

    try:
        encoded_jwt = jwt.encode(to_encode, SECRET_KEY, algorithm=ALGORITHM)  # type: ignore[possibly-unbound]
        return encoded_jwt
    except Exception as e:  # pylint: disable=broad-exception-caught
        logger.error("Failed to create access token: %s", e)
        raise ValueError("Failed to create access token") from e


def create_refresh_token(data: Dict[str, Any]) -> str:
    """Create a new refresh token."""
    if not JWT_AVAILABLE:
        raise ValueError("JWT not available")
    to_encode = data.copy()
    expire = datetime.utcnow() + timedelta(days=REFRESH_TOKEN_EXPIRE_DAYS)

    to_encode.update({
        "exp": expire,
        "iat": datetime.utcnow(),
        "type": "refresh"
    })

    try:
        encoded_jwt = jwt.encode(to_encode, SECRET_KEY, algorithm=ALGORITHM)  # type: ignore[possibly-unbound]
        return encoded_jwt
    except Exception as e:  # pylint: disable=broad-exception-caught
        logger.error("Failed to create refresh token: %s", e)
        raise ValueError("Failed to create refresh token") from e


def verify_token(token: str) -> Optional[Dict[str, Any]]:
    """Verify a JWT token and return the payload."""
    if not JWT_AVAILABLE:
        return None
    try:
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])  # type: ignore[possibly-unbound]
        return payload
    except JWTError as e:  # type: ignore[possibly-unbound]
        logger.warning("Token verification failed: %s", e)
        return None
    except Exception as e:  # pylint: disable=broad-exception-caught
        logger.error("Unexpected token error: %s", e)
        return None


# In-memory user storage (replace with database in production)
# Format: {username: {"hashed_password": str, "email": str, "full_name": str}}
fake_users_db: Dict[str, Dict[str, str]] = {}


def get_user(db: Dict[str, Dict[str, str]], username: str) -> Optional[Dict[str, str]]:
    """Get a user from the database."""
    return db.get(username)


def authenticate_user(db: Dict[str, Dict[str, str]], username: str, password: str) -> Optional[Dict[str, str]]:
    """Authenticate a user by username and password."""
    user = get_user(db, username)
    if not user:
        return None
    if not verify_password(password, user["hashed_password"]):
        return None
    return user


def create_user(db: Dict[str, Dict[str, str]], username: str, password: str,
                email: Optional[str] = None, full_name: Optional[str] = None) -> Optional[Dict[str, str]]:
    """Create a new user."""
    if username in db:
        return None  # User already exists

    hashed_password = get_password_hash(password)
    user_data = {
        "hashed_password": hashed_password
    }

    if email:
        user_data["email"] = email
    if full_name:
        user_data["full_name"] = full_name

    db[username] = user_data
    return user_data
