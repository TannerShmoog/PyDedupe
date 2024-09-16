import tkinter as tk
import os
from modules.constants import *


def resetUIState(app):
    # Disable all elements, then re-enable if valid
    app.hash_directory_button.config(state=tk.DISABLED)

    app.start_dedupe_button.config(state=tk.DISABLED)
    app.prev_dedupe_button.config(state=tk.DISABLED)
    app.next_dedupe_button.config(state=tk.DISABLED)
    app.stop_dedupe_button.config(state=tk.DISABLED)
    app.duplicate_groups_label.config(text="")

    app.prev_image_button.config(state=tk.DISABLED)
    app.next_image_button.config(state=tk.DISABLED)
    app.keep_checkbox.config(state=tk.DISABLED)
    app.delete_button.config(state=tk.DISABLED)
    app.open_button.config(state=tk.DISABLED)
    app.current_duplicates_label.config(text="")
    app.current_file_name_label.config(text="")
    app.current_file_dimensions_label.config(text="")
    app.current_file_length_label.config(text="")
    app.video_warning_label.config(text="")


def isDuplicatesDefined(app, must_be_deduping=True):
    # This is basically for the start button, we want to be *not*
    # Deduping in that case, no others
    if not app.currently_deduping and must_be_deduping:
        return False

    if (not app.duplicates
            or not isinstance(app.duplicates, list)
            or len(app.duplicates) < 1):
        return False

    return True


def isCurrentDuplicatesDefined(app):
    if not isDuplicatesDefined(app):
        return False

    if (not app.current_duplicates
            or not isinstance(app.current_duplicates, list)
            or len(app.current_duplicates) < 1):
        return False

    return True


def checkHashButton(app):
    if app.currently_deduping:
        return False

    if not app.validate_directory():
        return False

    if hasattr(app, "hash_thread"):
        if app.hash_thread.is_alive():
            return False

    return True


def updateHashButton(app):
    if checkHashButton(app):
        app.hash_directory_button.config(state=tk.NORMAL)


def checkStartButton(app):
    if not isDuplicatesDefined(app, must_be_deduping=False):
        return False

    return True


def updateStartButton(app):
    if checkStartButton(app):
        app.start_dedupe_button.config(state=tk.NORMAL)


def checkStopButton(app):
    if not app.currently_deduping:
        return False

    return True


def updateStopButton(app):
    if checkStopButton(app):
        app.stop_dedupe_button.config(state=tk.NORMAL)


def checkNextGroupButton(app):
    if not isDuplicatesDefined(app):
        return False

    if (app.index is None
            or app.index + 1 >= len(app.duplicates)):
        return False

    return True


def updateNextGroupButton(app):
    if checkNextGroupButton(app):
        app.next_dedupe_button.config(state=tk.NORMAL)


def checkPrevGroupButton(app):
    if not isDuplicatesDefined(app):
        return False

    if (app.index is None
            or app.index < 1):
        return False

    return True


def updatePrevGroupButton(app):
    if checkPrevGroupButton(app):
        app.prev_dedupe_button.config(state=tk.NORMAL)


def checkGroupsLabel(app):
    if not isDuplicatesDefined(app):
        return False

    if (app.index < 0
            or app.index >= len(app.duplicates)):
        return False

    return True


def updateGroupsLabel(app):
    if checkGroupsLabel(app):
        app.duplicate_groups_label.config(
            text=f"[{app.index + 1}/{len(app.duplicates)}]")


def checkNextImageButton(app):
    if not isCurrentDuplicatesDefined(app):
        return False

    if (app.current_image_index is None
            or app.current_image_index + 1 >= len(app.current_duplicates)):
        return False

    return True


def updateNextImageButton(app):
    if checkNextImageButton(app):
        app.next_image_button.config(state=tk.NORMAL)


def checkPrevImageButton(app):
    if not isCurrentDuplicatesDefined(app):
        return False

    if (app.current_image_index is None
            or app.current_image_index < 1):
        return False

    return True


def updatePrevImageButton(app):
    if checkPrevImageButton(app):
        app.prev_image_button.config(state=tk.NORMAL)


def checkKeepToggle(app):
    if not isCurrentDuplicatesDefined(app):
        return False

    if (app.current_image_index is None
            or not app.current_duplicates[app.current_image_index].image):
        return False

    return True


def updateKeepToggle(app):
    if checkKeepToggle(app):
        app.keep_checkbox.config(state=tk.NORMAL)
        current_state = app.current_duplicates[app.current_image_index].should_keep
        app.keep_checkbox_var.set(current_state)


def checkDeleteButton(app):
    if not isCurrentDuplicatesDefined(app):
        return False

    if all(item.should_keep for item in app.current_duplicates):
        return False

    return True


def updateDeleteButton(app):
    if checkDeleteButton(app):
        app.delete_button.config(state=tk.NORMAL)


def checkOpenButton(app):
    if not isCurrentDuplicatesDefined(app):
        return False

    if (app.current_image_index < 0
            or app.current_image_index >= len(app.current_duplicates)):
        return False

    file_path = os.path.join(
        app.dir, app.current_duplicates[app.current_image_index].file_name)
    if not os.path.exists(file_path):
        return False

    return True


def updateOpenButton(app):
    if checkOpenButton(app):
        app.open_button.config(state=tk.NORMAL)


def checkCurrentFileLabels(app):
    if not isCurrentDuplicatesDefined(app):
        return False

    if (app.current_image_index < 0
            or app.current_image_index >= len(app.current_duplicates)):
        return False

    return True


def updateCurrentFileLabels(app):
    if checkCurrentFileLabels(app):
        # x / y
        app.current_duplicates_label.config(
            text=f"[{app.current_image_index + 1}/{len(app.current_duplicates)}]")

        # Filename
        current_image_name = app.current_duplicates[app.current_image_index].file_name
        app.current_file_name_label.config(text=f"{current_image_name}")

        # File dims
        current_image_dims = app.current_duplicates[app.current_image_index].dims_string
        app.current_file_dimensions_label.config(text=f"{current_image_dims}")

        # File length
        current_image_length = app.current_duplicates[app.current_image_index].length_string
        app.current_file_length_label.config(text=f"{current_image_length}")

        # Video warning
        if any(current_image_name.lower().endswith(suffix) for suffix in VIDEO_FORMATS):
            app.video_warning_label.config(text="Video file!")


def checkWEBPButton(app):
    if app.currently_deduping:
        return False

    if not app.validate_directory():
        return False

    if hasattr(app, "hash_thread"):
        if app.hash_thread.is_alive():
            return False

    return True


def updateWEBPButton(app):
    if checkWEBPButton(app):
        app.webp_convert_button.config(state=tk.NORMAL)
