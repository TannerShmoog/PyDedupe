import functools
import time
from loguru import logger
import traceback
import logging

"""LOGGER"""
# Configure the logger
_logger = logger
_logger.add("log.txt", rotation="10 MB", level="TRACE", retention=1)


def trace(func):
    """
    Adds detailed logging and execution time measurement to a function.

    This decorator wraps the given function and automatically logs information
    about its calls and execution. The logged messages include:

        - Function name
        - Arguments and keyword arguments passed
        - Execution time
        - Return value of the function
        - Any exceptions raised during execution

    Args:
        func (function): The function to be wrapped and decorated.

    Returns:
        function: A wrapped version of the function with logging and timing.
    """
    @functools.wraps(func)
    def wrapper(*args, **kwargs):
        """
        Defines the logging wrapper for a function to be returned by the decorator.

        Args:
            func (function): The function to be wrapped.

        Returns:
            function: The result of the original function.
        """
        try:
            call_stack_id = id(wrapper)  # Unique ID for call stack grouping

            pre_log_output = f"\n[Call Stack {call_stack_id}] --- {func.__name__} CALLED ---"
            if args:
                pre_log_output += f"\nargs: {args}"
            if kwargs:
                pre_log_output += f"\nkwargs: {kwargs}"
            _logger.trace(pre_log_output)

            start_time = time.time()
            result = func(*args, **kwargs)
            end_time = time.time()

            post_log_output = f"\n[Call Stack {call_stack_id}] --- {func.__name__} ENDED ---"
            post_log_output += f"\ntook: {end_time - start_time:.4f} seconds"
            post_log_output += f"\nreturned: {result}"
            _logger.trace(post_log_output)

            return result
        except Exception as e:
            _logger.exception(e)
            print_to_scrolltext(
                f"Error in function {func.__name__}: {e}", color="red")
    return wrapper


def log_and_print(message):
    """
    Easy call to both print to console and log error messages.
    """
    global _logger
    print(message)
    _logger.exception(message)


def handle_exceptions(func):
    """
    Wraps a function to enclose its execution in a try-except block.
    If an exception occurs, it prints the exception details to the console.

    Args:
        func: The function to wrap.

    Returns:
        A wrapper function that executes the original function with error handling.
    """

    def wrapper(*args, **kwargs):
        try:
            return func(*args, **kwargs)
        except Exception as e:
            print_to_scrolltext(
                f"Error in function {func.__name__}: {e}", color="red")
            traceback.print_exc()  # Print detailed traceback
    return wrapper


"""
This code allows functions in modules to access our tkinter app class'
display_error from outside of the main module, in order to send messages to our scrolltext.
"""
_app = None


def initialize(app):
    global _app
    _app = app


def print_to_scrolltext(message, color="black"):
    """
    Temporarily enables a ScrolledText widget for output, appends a message,
    scrolls to the end, and then disables the widget.

    Args:
        app: The Tkinter application instance.
        message (str): The message to output to the console. 
    """
    if _app is None:
        raise RuntimeError("Console outputter not initialized")

    print(message)

    # Temporarily enable the scrolltext
    _app.console_output.configure(state='normal')

    # Create a tag for the colored text
    _app.console_output.tag_configure(color, foreground=color)

    # Append the message and a newline
    _app.console_output.insert("end", message + '\n', color)

    # Scroll to the end
    _app.console_output.see("end")

    # Disable editing again
    _app.console_output.configure(state='disabled')
