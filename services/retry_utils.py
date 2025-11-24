"""
Retry utilities for handling transient failures with exponential backoff
"""
import time
import random
from functools import wraps
from typing import Callable, Any, Optional, Type, Tuple

def exponential_backoff_retry(
    max_retries: int = 3,
    initial_delay: float = 1.0,
    max_delay: float = 30.0,
    backoff_factor: float = 2.0,
    jitter: bool = True,
    exceptions: Tuple[Type[Exception], ...] = (Exception,)
) -> Callable:
    """
    Decorator for retrying functions with exponential backoff
    
    Args:
        max_retries: Maximum number of retry attempts
        initial_delay: Initial delay in seconds
        max_delay: Maximum delay in seconds
        backoff_factor: Factor to multiply delay by after each retry
        jitter: Add random jitter to prevent thundering herd
        exceptions: Tuple of exceptions to catch and retry
    
    Returns:
        Decorated function with retry logic
    """
    def decorator(func: Callable) -> Callable:
        @wraps(func)
        def wrapper(*args, **kwargs) -> Any:
            delay = initial_delay
            last_exception = None
            
            for attempt in range(max_retries + 1):
                try:
                    return func(*args, **kwargs)
                except exceptions as e:
                    last_exception = e
                    
                    if attempt == max_retries:
                        print(f"❌ Max retries ({max_retries}) reached for {func.__name__}. Final error: {e}")
                        raise
                    
                    # Calculate next delay with exponential backoff
                    if jitter:
                        actual_delay = delay * (1 + random.uniform(-0.1, 0.1))
                    else:
                        actual_delay = delay
                    
                    print(f"⚠️ Attempt {attempt + 1}/{max_retries + 1} failed for {func.__name__}: {e}")
                    print(f"⏳ Retrying in {actual_delay:.2f} seconds...")
                    
                    time.sleep(actual_delay)
                    
                    # Increase delay for next retry
                    delay = min(delay * backoff_factor, max_delay)
            
            # This should never be reached, but just in case
            if last_exception:
                raise last_exception
                
        return wrapper
    return decorator


def retry_with_backoff(
    func: Callable,
    args: tuple = (),
    kwargs: dict = None,
    max_retries: int = 3,
    initial_delay: float = 1.0,
    max_delay: float = 30.0,
    backoff_factor: float = 2.0,
    exceptions: Tuple[Type[Exception], ...] = (Exception,)
) -> Any:
    """
    Function to retry a callable with exponential backoff (non-decorator version)
    
    Args:
        func: Function to retry
        args: Positional arguments for the function
        kwargs: Keyword arguments for the function
        max_retries: Maximum number of retry attempts
        initial_delay: Initial delay in seconds
        max_delay: Maximum delay in seconds
        backoff_factor: Factor to multiply delay by after each retry
        exceptions: Tuple of exceptions to catch and retry
    
    Returns:
        Result of the function call
    """
    if kwargs is None:
        kwargs = {}
    
    delay = initial_delay
    last_exception = None
    
    for attempt in range(max_retries + 1):
        try:
            return func(*args, **kwargs)
        except exceptions as e:
            last_exception = e
            
            if attempt == max_retries:
                print(f"❌ Max retries ({max_retries}) reached. Final error: {e}")
                raise
            
            # Calculate next delay with exponential backoff
            actual_delay = delay * (1 + random.uniform(-0.1, 0.1))
            
            print(f"⚠️ Attempt {attempt + 1}/{max_retries + 1} failed: {e}")
            print(f"⏳ Retrying in {actual_delay:.2f} seconds...")
            
            time.sleep(actual_delay)
            
            # Increase delay for next retry
            delay = min(delay * backoff_factor, max_delay)
    
    if last_exception:
        raise last_exception


class RetryableError(Exception):
    """Base exception for errors that should be retried"""
    pass


class RateLimitError(RetryableError):
    """Exception for rate limit errors that should be retried with backoff"""
    pass


class TransientNetworkError(RetryableError):
    """Exception for transient network errors that should be retried"""
    pass