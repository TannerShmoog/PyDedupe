import os
import math
import io
import cv2
import queue
import logging
import threading
import shutil
from datetime import timedelta
from send2trash import send2trash
from PIL import Image, ImageTk
import tkinter as tk
from tkinter import font as tkFont
from tkinter import filedialog, scrolledtext, messagebox
from modules.customhasher import VideoAwarePHash
from modules.constants import *
from modules.wrappers import handle_exceptions, initialize, print_to_scrolltext
from modules.queuehandler import QueueHandler
from modules.fileitem import FileItem
from modules.ui_state import *


class MainWindow(tk.Frame):
    def __init__(self, root=None):
        super().__init__(root)
        self.root = root
        self.debug = False

        # IMPORTANT INITIAL VARS
        self.dir = None
        self.currently_deduping = False
        self.index = None
        self.duplicates = None
        self.current_duplicates = None
        self.current_image_index = None
        self.photo = None
        self.banner_images = None
        self.icons = {}

        # Load ui icons
        self.load_icons()

        # Set up the window
        self.root.title("Image De-duplicator")
        self.window_width = 900
        self.window_height = 800
        self.root.geometry(f"{self.window_width}x{self.window_height}")

        # Resize event binding to control size of image canvas
        self.root.bind('<Configure>', self.on_resize)

        # Keybinds
        root.bind('<Key>', lambda event: self.handle_keybinds(event))
        root.bind('<Button-1>', lambda event: self.handle_button1(event))

        # Width of current image indicator bar
        self.indicator_width = 5

        # Console output container frame
        self.console_output_container = tk.Frame(self.root, background="red")
        self.console_output_container.pack(
            side=tk.TOP, fill=tk.X, expand=False)

        # Bottom bar for resizing
        @handle_exceptions
        def start_resize(event):
            self._drag_start_y = event.y
            self._start_height = self.console_output_container.winfo_height()

        @handle_exceptions
        def perform_resize(event):
            delta = event.y - self._drag_start_y

            # Get the height of a single line of text
            # Assuming [3] is the line height including spacing
            line_height = self.console_output.dlineinfo('1.0')[3]

            new_height_pixels = self._start_height + delta
            # Convert the new height in pixels to the number of lines
            # Ensure at least 1 line
            new_height_lines = new_height_pixels // line_height
            print(new_height_lines)
            self.console_output.pack_forget()
            if new_height_lines <= 0:
                self.console_output.pack_forget()
            else:
                self.console_output.config(height=new_height_lines)
                self.console_output.pack(
                    side=tk.TOP, fill=tk.BOTH, expand=True)

            self.update_idletasks()
            self.display_image()

        self.grip = tk.Frame(self.console_output_container, height=5,
                             bg="grey", cursor="sb_v_double_arrow")
        self.grip.pack(side=tk.BOTTOM, fill=tk.X)
        self.grip.bind("<Button-1>", start_resize)
        self.grip.bind("<ButtonRelease-1>", perform_resize)

        self._drag_start_y = 0
        self._start_height = 0

        # Console output scrolltext
        self.console_output = scrolledtext.ScrolledText(
            self.console_output_container, height=1, background="purple", state=tk.DISABLED)
        self.console_output.pack(
            side=tk.TOP, fill=tk.BOTH, expand=True)

        # Set up logging to write to the queue
        self.log_queue = queue.Queue()
        self.poll_queue()
        queue_handler = QueueHandler(self.log_queue)
        logging.basicConfig(level=logging.INFO, handlers=[queue_handler])

        # Directory frame
        self.directory_frame = tk.Frame(self.root, background="green")
        self.directory_frame.pack(side=tk.TOP, fill=tk.X)

        # Choose directory button
        self.choose_button = tk.Button(
            self.directory_frame,
            text="Choose",
            command=self.select_directory,
            image=self.icons["choose_folder.png"],
            compound=tk.LEFT)
        self.choose_button.pack(side=tk.LEFT, padx=5, pady=5)

        # Directory text entry
        self.directory_entry = tk.Entry(self.directory_frame, width=50)
        self.directory_entry.pack(side=tk.LEFT, padx=5, pady=5)
        self.directory_entry.bind('<KeyRelease>', self.validate_directory)

        # WEBP convert button
        self.webp_convert_button = tk.Button(
            self.directory_frame,
            text="Convert WEBP",
            command=self.convert_webp_to_png,
            image=self.icons["hash.png"],
            compound=tk.LEFT)
        self.webp_convert_button.pack(side=tk.LEFT, padx=5, pady=5)
        self.webp_convert_button.config(state=tk.DISABLED)

        # Hash directory button
        self.hash_directory_button = tk.Button(
            self.directory_frame,
            text="Hash Directory",
            command=self.start_hashing,
            image=self.icons["hash.png"],
            compound=tk.LEFT)
        self.hash_directory_button.pack(side=tk.LEFT, padx=5, pady=5)
        self.hash_directory_button.config(state=tk.DISABLED)

        # Slider for integer values between 1 and 30
        self.hash_distance_slider = tk.Scale(
            self.directory_frame,  # Parent frame
            from_=1,               # Minimum value
            to=30,                 # Maximum value
            orient=tk.HORIZONTAL,  # Horizontal slider
            label="Select Value"    # Label for the slider
        )
        self.hash_distance_slider.pack(side=tk.LEFT, padx=5, pady=5)
        self.hash_distance_slider.set(10)  # Set default value to 1

        # Timestamp miniframe
        self.timestamp_entry_frame = tk.Frame(self.directory_frame)
        self.timestamp_entry_frame.pack(side=tk.LEFT, padx=5, pady=5)

        # Timestamp text entry
        self.timestamp_entry = tk.Entry(
            self.timestamp_entry_frame,
            width=7,
            validate=tk.ALL,
            validatecommand=(root.register(
                self.validate_numerical_entry), '%P', 5)
        )
        self.timestamp_entry.pack(side=tk.LEFT)

        # Timestamp label
        self.timestamp_entry_label = tk.Label(
            self.timestamp_entry_frame,
            text="Use Frame at Timestamp",
            image=self.icons["film.png"],
            compound=tk.LEFT)
        self.timestamp_entry_label.pack(side=tk.LEFT)

        # First frame checkbox
        self.first_frame_checkbox_var = tk.BooleanVar()
        self.first_frame_checkbox = tk.Checkbutton(
            self.directory_frame,
            text="Use First Frame",
            variable=self.first_frame_checkbox_var,
            image=self.icons["film.png"],
            compound=tk.LEFT,)
        self.first_frame_checkbox.pack(side=tk.LEFT, padx=5, pady=5)
        self.first_frame_checkbox.config()

        # Last frame checkbox
        self.last_frame_checkbox_var = tk.BooleanVar()
        self.last_frame_checkbox = tk.Checkbutton(
            self.directory_frame,
            text="Use Last Frame",
            variable=self.last_frame_checkbox_var,
            image=self.icons["film.png"],
            compound=tk.LEFT,)
        self.last_frame_checkbox.pack(side=tk.LEFT, padx=5, pady=5)
        self.last_frame_checkbox.config()

        # Duplicate group frame
        self.dedupe_frame = tk.Frame(self.root, background="purple")
        self.dedupe_frame.pack(side=tk.TOP, fill=tk.X)

        # Start deduping button
        self.start_dedupe_button = tk.Button(
            self.dedupe_frame,
            text="Start",
            command=self.start_deduping,
            image=self.icons["start.png"],
            compound=tk.LEFT)
        self.start_dedupe_button.pack(side=tk.LEFT, padx=5, pady=5)
        self.start_dedupe_button.config(state=tk.DISABLED)

        # Previous duplicate group button
        self.prev_dedupe_button = tk.Button(
            self.dedupe_frame,
            text="Previous Group",
            command=self.prev_deduping,
            image=self.icons["left.png"],
            compound=tk.LEFT)
        self.prev_dedupe_button.pack(side=tk.LEFT, padx=5, pady=5)
        self.prev_dedupe_button.config(state=tk.DISABLED)

        # Duplicate groups label
        self.duplicate_groups_label = tk.Label(
            self.dedupe_frame, text="", width=10)
        self.duplicate_groups_label.pack(side=tk.LEFT, padx=5, pady=5)

        # Next duplicate group button
        self.next_dedupe_button = tk.Button(
            self.dedupe_frame,
            text="Next Group",
            command=self.next_deduping,
            image=self.icons["right.png"],
            compound=tk.LEFT)
        self.next_dedupe_button.pack(side=tk.LEFT, padx=5, pady=5)
        self.next_dedupe_button.config(state=tk.DISABLED)

        # Stop deduping button
        self.stop_dedupe_button = tk.Button(
            self.dedupe_frame,
            text="Stop",
            command=self.stop_deduping,
            image=self.icons["stop.png"],
            compound=tk.LEFT)
        self.stop_dedupe_button.pack(side=tk.LEFT, padx=5, pady=5)
        self.stop_dedupe_button.config(state=tk.DISABLED)

        # Current duplicate group frame
        self.step_image_frame = tk.Frame(self.root, background="green")
        self.step_image_frame.pack(side=tk.TOP, fill=tk.X)

        # Previous image button
        self.prev_image_button = tk.Button(
            self.step_image_frame,
            text="Previous Image",
            command=self.prev_image,
            image=self.icons["left.png"],
            compound=tk.LEFT)
        self.prev_image_button.pack(side=tk.LEFT, padx=5, pady=5)
        self.prev_image_button.config(state=tk.DISABLED)

        # Current duplicates
        self.current_duplicates_label = tk.Label(
            self.step_image_frame, text="", width=10)
        self.current_duplicates_label.pack(side=tk.LEFT, padx=5, pady=5)

        # Next image button
        self.next_image_button = tk.Button(
            self.step_image_frame,
            text="Next Image",
            command=self.next_image,
            image=self.icons["right.png"],
            compound=tk.LEFT)
        self.next_image_button.pack(side=tk.LEFT, padx=5, pady=5)
        self.next_image_button.config(state=tk.DISABLED)

        # Keep image checkbox
        self.keep_checkbox_var = tk.BooleanVar()
        self.keep_checkbox = tk.Checkbutton(
            self.step_image_frame,
            text="Keep",
            variable=self.keep_checkbox_var,
            command=self.update_current_image_state,
            image=self.icons["lock_closed.png"],
            compound=tk.LEFT,)
        self.keep_checkbox.pack(side=tk.LEFT, padx=5, pady=5)
        self.keep_checkbox.config(state=tk.DISABLED)

        # Delete unselected button
        self.delete_button = tk.Button(
            self.step_image_frame,
            text="Delete Unselected Images",
            command=self.delete_unselected,
            image=self.icons["delete.png"],
            compound=tk.LEFT)
        self.delete_button.pack(side=tk.LEFT, padx=5, pady=5)
        self.delete_button.config(state=tk.DISABLED)

        # Open file button
        self.open_button = tk.Button(
            self.step_image_frame,
            text="Open File",
            command=self.open_current_file,
            image=self.icons["open_file.png"],
            compound=tk.LEFT)
        self.open_button.pack(side=tk.LEFT, padx=5, pady=5)
        self.open_button.config(state=tk.DISABLED)

        # Current file info frame
        self.current_file_info_frame = tk.Frame(self.step_image_frame)
        self.current_file_info_frame.pack(side=tk.LEFT, padx=5, pady=5)

        # Current file name label
        self.current_file_name_label = tk.Label(
            self.current_file_info_frame,
            text="",
            font=tkFont.Font(family="Helvetica", size=12, weight="bold")
        )
        self.current_file_name_label.pack(side=tk.TOP, padx=5, pady=5)

        # Current file dimensions label
        self.current_file_dimensions_label = tk.Label(
            self.current_file_info_frame,
            text="",
            font=tkFont.Font(family="Helvetica", size=12, weight="bold")
        )
        self.current_file_dimensions_label.pack(side=tk.TOP, padx=5, pady=5)

        # Current file length label
        self.current_file_length_label = tk.Label(
            self.current_file_info_frame,
            text="",
            font=tkFont.Font(family="Helvetica", size=12, weight="bold")
        )
        self.current_file_length_label.pack(side=tk.TOP, padx=5, pady=5)

        # Video warning label
        self.video_warning_label = tk.Label(
            self.step_image_frame,
            text="",
            font=tkFont.Font(family="Helvetica", size=12, weight="bold"),
            fg="red")
        self.video_warning_label.pack(side=tk.LEFT, padx=5, pady=5)

        # Display area frame
        self.display_frame = tk.Frame(self.root, background="red")
        self.display_frame.pack(side=tk.BOTTOM, fill=tk.BOTH, expand=True)

        # Image Canvas
        self.image_canvas = tk.Canvas(self.display_frame, background="blue")
        self.image_canvas.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)

        # Frame to hold the image banner
        self.banner_frame = tk.Frame(
            self.display_frame)
        self.banner_frame.pack(side=tk.RIGHT, fill=tk.Y)

        # Canvas for scrolling the banner (if needed)
        self.banner_canvas = tk.Canvas(
            self.banner_frame, background="green", width=200)
        self.banner_canvas.pack(
            side=tk.LEFT, fill=tk.BOTH, expand=True, padx=5)

        # Inner frame within the canvas to hold the images
        self.banner_inner_frame = tk.Frame(self.banner_canvas)
        self.banner_canvas.create_window(
            (0, 0), window=self.banner_inner_frame, anchor=tk.NW)

        # Scrollbar for the canvas
        self.banner_scrollbar = tk.Scrollbar(
            self.banner_frame, orient=tk.VERTICAL, command=self.banner_canvas.yview)
        self.banner_scrollbar.pack(side=tk.RIGHT, fill=tk.Y)

        self.banner_canvas.configure(yscrollcommand=self.banner_scrollbar.set)

        def on_mousewheel(event):
            # Check if the scrollable content exceeds the canvas size
            scroll_region = self.banner_canvas.cget("scrollregion").split()
            if not scroll_region:
                return
            scroll_region_height = int(scroll_region[3])-int(scroll_region[1])
            if scroll_region_height > self.banner_canvas.winfo_height():
                self.banner_canvas.yview_scroll(
                    int(-1*(event.delta/120)), "units")
        self.banner_canvas.bind_all("<MouseWheel>", on_mousewheel)

    def load_icons(self):
        for filename in os.listdir(ICON_DIR):
            image = Image.open(os.path.join(ICON_DIR, filename))
            image = image.resize((16, 16), Image.LANCZOS)
            icon = ImageTk.PhotoImage(image)
            self.icons[filename] = icon

    def poll_queue(self):
        while not self.log_queue.empty():
            log_entry = self.log_queue.get_nowait()
            print_to_scrolltext(log_entry)
        self.after(100, self.poll_queue)

    @handle_exceptions
    def handle_button1(self, event):
        if event.widget != self.directory_entry and event.widget != self.timestamp_entry:
            event.widget.winfo_toplevel().focus_set()
        return "break"

    @handle_exceptions
    def handle_keybinds(self, event):
        if self.directory_entry is not self.root.focus_get():
            if event.keysym == 'Down':
                if self.next_dedupe_button.cget("state") == tk.NORMAL:
                    self.next_deduping()
            elif event.keysym == 'Up':
                if self.prev_dedupe_button.cget("state") == tk.NORMAL:
                    self.prev_deduping()
            elif event.keysym == 'Right':
                if self.next_image_button.cget("state") == tk.NORMAL:
                    self.next_image()
            elif event.keysym == 'Left':
                if self.prev_image_button.cget("state") == tk.NORMAL:
                    self.prev_image()
            elif event.keysym == 'Return':
                if self.start_dedupe_button.cget("state") == tk.NORMAL:
                    self.start_deduping()
            elif event.keysym == 'Tab':
                pass
            elif event.keysym == 'space':
                if self.keep_checkbox.cget("state") == tk.NORMAL:
                    self.keep_checkbox_var.set(
                        not self.keep_checkbox_var.get())
                    self.update_current_image_state()
            elif event.keysym == 'Escape':
                if self.stop_dedupe_button.cget("state") == tk.NORMAL:
                    self.stop_deduping()
            elif event.keysym == "Delete":
                if self.delete_button.cget("state") == tk.NORMAL:
                    self.delete_unselected()

            else:
                # Let Tkinter handle the key event normally
                return "break"
        else:
            # Let Tkinter handle the key event normally
            return "break"

    @handle_exceptions
    def on_resize(self, event=None):
        if event.widget != self.root:
            return

        if event.height and event.width:
            if event.height == self.window_height and event.width == self.window_width:
                return
            else:
                self.window_height = event.height
                self.window_width = event.width

        if not self.current_duplicates:
            return

        total_height = self.root.winfo_height()
        other_widgets_height = sum([widget.winfo_height(
        ) for widget in self.root.winfo_children() if widget != self.image_canvas])
        max_canvas_height = total_height - other_widgets_height

        # Adjust canvas size
        self.image_canvas.config(height=max_canvas_height)

        # Resize and display the image if one is loaded
        if self.current_duplicates[self.current_image_index].image:
            if hasattr(self, 'resize_timer') and self.resize_timer is not None:
                self.resize_timer.cancel()

            @handle_exceptions
            def resize_and_display():
                self.display_image()
                # Clear the timer
                self.resize_timer = None

            # Delay 0.01 seconds
            self.resize_timer = threading.Timer(
                0.01, resize_and_display)
            self.resize_timer.start()

    @handle_exceptions
    def select_directory(self):
        directory = filedialog.askdirectory(title="Select Directory")
        if directory:
            self.directory_entry.delete(0, tk.END)
            self.directory_entry.insert(0, directory)
            self.validate_directory()
            self.update_dedupe_button_state()

    @handle_exceptions
    def validate_directory(self, event=None):
        if self.currently_deduping:
            return False

        directory = self.directory_entry.get()
        # invalid
        if not os.path.isdir(directory):
            self.directory_entry.config(fg='red')
            self.dir = None
            return False
        # valid
        else:
            self.directory_entry.config(fg='black')
            self.dir = directory
            return True

    def validate_numerical_entry(self, value, maxlen=None):
        """
        Checks that a string (taken from a tk.Entry object) is convertable to an integer,
        and optionally if it is longer than maxlen digits long.

        Args:
            values (int): The string value of the Entry widget.
            maxlen (int): (optional) The maximum digit length of the integer.

        Returns:
            valid (bool): True if the string represented a valid integer with the correct length, otherwise False.
        """
        try:
            if value == "":
                return True
            if maxlen:
                maxlen = int(maxlen)
            else:
                maxlen = math.inf
            if len(value) > maxlen:
                return False
            value = int(value)
            return True
        except Exception as e:
            return False

    @handle_exceptions
    def _process_videos_with_frame(self, phasher: VideoAwarePHash, frame_type: str):
        """Processes videos using specified frame and suffixes filenames"""
        encodings = phasher.encode_images(image_dir=self.dir, recursive=True,
                                          use_first_frame=(
                                              frame_type == "first"),
                                          use_last_frame=(
                                              frame_type == "last"),
                                          frame_timestamp_seconds=int(frame_type) if frame_type.isdigit() else None)
        # Add suffix to video hashes
        return {f"{k}//{frame_type}": v for k, v in encodings.items()}

    @handle_exceptions
    def clean_duplicate_group_video_suffixes(self, group):
        result = {}  # Use a dictionary to track unique prefixes and their suffixes
        for filename in group:
            prefix, _, suffix = filename.partition('//')
            result[prefix] = True

        return [prefix for prefix in result.keys()]

    @handle_exceptions
    def hash_directory(self):
        if self.debug:
            self.duplicates = [['8 - Copy (2).jpg', '8 - Copy - Copy.jpg', '8 - Copy.jpg', '8.jpg'], ['4.jpg', '5 - Copy.jpg', '5.jpg'], [
                'v2.webm', 'v2_first_frame.jpg'], ['10.jpg', '11.jpg', '12.jpg', 'longlonglonglomglongfilenamelongname.jpg'], ['v1.mp4', 'v1_first_frame.jpg'], ['7 - Copy.gif', '7.gif']]
            self.start_dedupe_button.config(state=tk.NORMAL)
            return
        thread_stdout = io.StringIO()
        log_handler = logging.StreamHandler(thread_stdout)
        logger = logging.getLogger()
        logger.addHandler(log_handler)
        try:
            use_first_frame = self.first_frame_checkbox_var.get()
            use_last_frame = self.last_frame_checkbox_var.get()
            timestamp_seconds_str = self.timestamp_entry.get()
            frame_timestamp_seconds = None
            if timestamp_seconds_str is not None and timestamp_seconds_str != "":
                frame_timestamp_seconds = int(timestamp_seconds_str)

            # phasher = PHash()
            # encodings = phasher.encode_images(image_dir=self.dir)
            # self.duplicates = phasher.find_duplicates(encoding_map=encodings)
            phasher = VideoAwarePHash()

            # Hash non-videos directly
            non_video_encodings = phasher.encode_images(
                image_dir=self.dir, recursive=True)
            print(str(non_video_encodings))
            print("-----------------")
            # Process videos separately based on frame selection
            video_encodings = {}
            if use_first_frame:
                first_frame_encodings = self._process_videos_with_frame(
                    phasher, "first")
                print(str(first_frame_encodings))
                print("-----------------")
                video_encodings.update(first_frame_encodings)
            if use_last_frame:
                last_frame_encodings = self._process_videos_with_frame(
                    phasher, "last")
                video_encodings.update(last_frame_encodings)
                print(str(last_frame_encodings))
                print("-----------------")
            if frame_timestamp_seconds is not None and frame_timestamp_seconds != "":
                timestamp_encodings = self._process_videos_with_frame(
                    phasher, str(frame_timestamp_seconds))
                print(str(timestamp_encodings))
                print("-----------------")
                video_encodings.update(timestamp_encodings)

            # Merge results
            merged_encodings = non_video_encodings.copy()
            merged_encodings.update(video_encodings)

            print(str(merged_encodings))
            print("-----------------")

            # Continue duplicate finding as before
            self.duplicates = phasher.find_duplicates(
                encoding_map=merged_encodings, recursive=True, max_distance_threshold=self.hash_distance_slider.get(), search_method='brute_force_cython')

            # convert to list for easy iteration
            self.duplicates = [[key, *values]
                               for key, values in self.duplicates.items() if values]

            self.duplicates = [self.clean_duplicate_group_video_suffixes(
                group) for group in self.duplicates]

            # Sort sublists and remove length 1 lists
            self.duplicates = [
                sorted(sublist) for sublist in self.duplicates if len(sublist) > 1]
            # Remove duplicate lists
            self.duplicates = [list(t) for t in set(
                tuple(sublist) for sublist in self.duplicates)]

            print_to_scrolltext(thread_stdout.getvalue())

            # show dupes and total number in console output
            print_to_scrolltext(str(self.duplicates))
            color = "black"
            if len(self.duplicates) == 0:
                color = "red"
            print_to_scrolltext(
                f"{len(self.duplicates)} duplicate groups found.", color)

            # self.hash_directory_button.config(state=tk.NORMAL)
            # Update the buttons in 100ms after to make sure the thread finishes
            self.root.after(100, self.update_dedupe_button_state)
        finally:
            logger.removeHandler(log_handler)

    @handle_exceptions
    def start_hashing(self):
        if hasattr(self, "hash_thread"):
            if self.hash_thread.is_alive():
                return
        if self.dir:
            self.root.focus()
            self.currently_deduping = False
            self.index = None
            self.duplicates = None
            self.current_duplicates = None
            self.current_image_index = None
            self.photo = None
            self.banner_images = None
            self.update_dedupe_button_state()
            self.hash_thread = threading.Thread(target=self.hash_directory)
            self.hash_thread.start()
            self.update_dedupe_button_state()
        else:
            pass  # TODO add invalid dir label

    @handle_exceptions
    def start_converting_webp(self):
        if hasattr(self, "hash_thread"):
            if self.hash_thread.is_alive():
                return
        if self.dir:
            self.root.focus()
            self.currently_deduping = False
            self.index = None
            self.duplicates = None
            self.current_duplicates = None
            self.current_image_index = None
            self.photo = None
            self.banner_images = None
            self.update_dedupe_button_state()
            self.hash_thread = threading.Thread(
                target=self.convert_webp_to_png)
            self.hash_thread.start()
            self.update_dedupe_button_state()
        else:
            pass  # TODO add invalid dir label

    @handle_exceptions
    def on_close(self):
        self.console_redirector.restore_stdout()
        self.root.destroy()

    @handle_exceptions
    def load_images(self):
        for item in self.current_duplicates:
            image_path = os.path.join(self.dir, item.file_name)

            # Check if it's a video file
            if os.path.splitext(image_path)[1].lower() in VIDEO_FORMATS:
                cap = cv2.VideoCapture(image_path)
                ret, frame = cap.read()
                # Try to get the video length
                try:
                    total_frames = cap.get(cv2.CAP_PROP_FRAME_COUNT)
                    fps = cap.get(cv2.CAP_PROP_FPS)
                    length = timedelta(seconds=round(total_frames / fps))
                    hh, mm, ss = length.seconds // 3600, length.seconds % 3600 // 60, length.seconds % 60
                    item.length_string = f"{hh:02d}:{mm:02d}:{ss:02d}"
                except:
                    item.length_string = ""
                cap.release()
                if ret:
                    image = Image.fromarray(
                        cv2.cvtColor(frame, cv2.COLOR_BGR2RGB))
                    # For use in banner images
                    image.filename = image_path
                else:
                    print(f"Error reading frame from video: {image_path}")
                    image = None
            else:
                image = Image.open(image_path)

            if image:
                # Store the image
                item.image = image
                # Set the dimensions string
                width, height = image.size
                item.dims_string = f"{width}x{height}"
                # Set the length string
            else:
                item.image = None
                item.dims_string = ""

        if (len(self.current_duplicates) > 0 and
                all(getattr(item, "image") not in [None, False] for item in self.current_duplicates)):
            self.update_banner()

    @handle_exceptions
    def update_banner(self):
        # Clear existing images
        for widget in self.banner_inner_frame.winfo_children():
            widget.destroy()

        # Add images to the banner
        self.banner_images = []
        max_width = self.banner_canvas.winfo_width() - self.indicator_width - 10
        for item in self.current_duplicates:
            image_copy = item.image.copy()

            # Calculate thumbnail dimensions
            width, height = image_copy.size
            max_height = int(max_width / (width / height))

            # Resize for display while maintaining aspect ratio
            image_copy.thumbnail((max_width, max_height))
            photo_img = ImageTk.PhotoImage(image_copy)

            # Container frame for each image and its selection indicator
            container_frame = tk.Frame(self.banner_inner_frame)
            container_frame.pack(pady=5)

            # Display file name
            file_name = tk.Label(
                container_frame, text=item.image.filename, anchor=tk.W)

            # Trim the filename to display just the file name without the preceding path
            filename_text = os.path.basename(item.image.filename)
            file_name.config(text=filename_text)

            # Measure to make sure the file name fits
            font = tkFont.Font(file_name)
            width = font.measure(file_name.cget("text"))

            truncated = False
            # Truncate the text by 1 character at a time until it fits
            while width > max_width:
                truncated = True
                filename_text = filename_text[:-1]
                width = font.measure(f"{filename_text}...")

            # Append "..." if the name is truncated
            if truncated:
                filename_text = filename_text + "..."
            file_name.config(text=filename_text)
            file_name.pack(side=tk.TOP, fill=tk.X)

            # Store a reference so it doesn't get garbage collected
            label = tk.Label(container_frame, image=photo_img)
            label.image = photo_img  # Keep a reference to avoid garbage collection
            label.pack(side=tk.LEFT)

            # Create the selection indicator (a red bar)
            selection_indicator = tk.Frame(
                container_frame, width=self.indicator_width, height=max_height, background="blue")
            selection_indicator.pack(side=tk.LEFT, fill=tk.Y)
            selection_indicator.pack_forget()

            label.indicator = selection_indicator
            self.banner_images.append(label)

        # Update canvas scrolling region, update_idletasks is needed to ensure all images are fully
        # rendered before updatind the scroll bar
        self.banner_inner_frame.update_idletasks()
        self.banner_canvas.config(scrollregion=self.banner_canvas.bbox(tk.ALL))

    @handle_exceptions
    def display_image(self):
        # sanity check
        if any(not getattr(item, "image") for item in self.current_duplicates):
            self.load_images()

        image = self.current_duplicates[self.current_image_index].image
        if image:
            # Get space available to canvas
            max_height = self.image_canvas.winfo_height()
            max_width = self.image_canvas.winfo_width()
            image_copy = image.copy()

            # Resize for display while maintaining aspect ratio
            image_copy.thumbnail((max_width, max_height), Image.LANCZOS)
            # Store a reference so it doesn't get garbage collected
            self.photo = ImageTk.PhotoImage(image_copy)

            # Update the canvas
            self.image_canvas.delete(tk.ALL)
            self.image_canvas.create_image(
                0, 0, anchor=tk.NW, image=self.photo)

            # Draw a bar to indicate current image
            for index, label in enumerate(self.banner_images):
                # Toggle visibility of the current indicator on
                if index == self.current_image_index:
                    label.indicator.pack(side=tk.LEFT, fill=tk.Y)
                # Toggle off for non current images
                else:
                    label.indicator.pack_forget()

        else:
            print("Error displaying image")

    @handle_exceptions
    def start_deduping(self):
        # Housekeeping
        self.currently_deduping = True
        self.index = 0

        # Current duplicate group housekeeping
        # Store as tuples to keep it easy to step through
        self.current_duplicates = [FileItem(file_name)
                                   for file_name in self.duplicates[self.index]]
        self.current_image_index = 0

        # Update canvas
        self.photo = None
        self.banner_images = None
        self.load_images()
        self.display_image()

        self.update_dedupe_button_state()

    @handle_exceptions
    def stop_deduping(self):
        # Housekeeping
        self.currently_deduping = False
        self.index = None

        # Current duplicate group housekeeping
        self.current_duplicates = None
        self.current_image_index = None
        self.photo = None
        self.banner_images = None

        self.update_dedupe_button_state()

    @handle_exceptions
    def next_deduping(self):
        # Housekeeping
        self.index += 1

        # Current duplicate group housekeeping
        # Store as tuples to keep it easy to step through
        self.current_duplicates = [FileItem(file_name)
                                   for file_name in self.duplicates[self.index]]
        self.current_image_index = 0

        # Update canvas
        self.photo = None
        self.banner_images = None
        self.load_images()
        self.display_image()

        self.update_dedupe_button_state()

    @handle_exceptions
    def prev_deduping(self):
        # Housekeeping
        self.index -= 1

        # Current duplicate group housekeeping
        # Store as tuples to keep it easy to step through
        self.current_duplicates = [FileItem(file_name)
                                   for file_name in self.duplicates[self.index]]
        self.current_image_index = 0

        # Update canvas
        self.photo = None
        self.banner_images = None
        self.load_images()
        self.display_image()

        self.update_dedupe_button_state()

    @handle_exceptions
    def next_image(self):
        # Current duplicate group housekeeping
        self.current_image_index += 1

        # Update canvas
        self.photo = None
        self.display_image()

        self.update_dedupe_button_state()

    @handle_exceptions
    def prev_image(self):
        # Current duplicate group housekeeping
        self.current_image_index -= 1

        # Update canvas
        self.photo = None
        self.display_image()

        self.update_dedupe_button_state()

    @handle_exceptions
    def update_current_image_state(self):
        checkbox_state = self.keep_checkbox_var.get()

        # 1th value is boolean whether to keep
        self.current_duplicates[self.current_image_index].should_keep = checkbox_state

        # Update the outline of the corresponding label in self.banner_images
        if self.banner_images:
            label = self.banner_images[self.current_image_index]
            if checkbox_state:
                # Clear outline - to be kept
                label.config(highlightthickness=0)
                self.keep_checkbox.config(image=self.icons["lock_closed.png"])
            else:
                # Add outline - to be deleted
                label.config(highlightthickness=4, highlightbackground="red")
                self.keep_checkbox.config(image=self.icons["lock_open.png"])

        self.update_dedupe_button_state()

    @handle_exceptions
    def asynchronous_delete(self, file_path):
        def attempt_delete(retries_left=3):  # Add retries_left parameter
            if retries_left > 0:
                try:
                    send2trash(file_path)
                    print_to_scrolltext(
                        f"Removed image: {file_path}", color="green")
                    return True
                except OSError:
                    if retries_left == 1:  # Only print failure message once
                        print_to_scrolltext(
                            f"Failed to remove image: {file_path}", color="red")
                    root.after(500, attempt_delete, retries_left - 1)
            return False

        root.after(100, attempt_delete)  # Initial delay of 100ms

    @handle_exceptions
    def delete_unselected(self):
        to_delete = []
        for item in self.current_duplicates:
            if not item.should_keep:
                to_delete.append(item.file_name)

        image_list_string = '\n'.join(to_delete)

        if len(to_delete) > 0:
            title = "Confirm Delete"
            message = f"The following images will be moved to the recycle bin:\n{image_list_string}"

            # User confirmation
            response = messagebox.askyesno(title, message)
            # User selected yes
            if response:
                for file_name in to_delete:
                    file_path = os.path.normpath(
                        os.path.join(self.dir, file_name))
                    # Recycle, don't delete, since it is a user endpoint
                    if os.path.exists(file_path):
                        # send2trash(file_path)
                        thread = threading.Thread(
                            target=self.asynchronous_delete, args=(file_path,))
                        thread.start()

                    # Remove all occurences of deleted file in self.duplicates
                    self.duplicates = [[item for item in sublist if item != file_name]
                                       for sublist in self.duplicates]

                # Clean up length < 2 duplicate groups
                filtered_duplicates = []
                for index, sublist in enumerate(self.duplicates):
                    # Keep groups length >= 2
                    if len(sublist) >= 2:
                        filtered_duplicates.append(sublist)
                    # Need to shift index down if we remove a duplicate group
                    # in front of current location
                    elif self.index > index:
                        self.index -= 1
                self.duplicates = filtered_duplicates

                # If no duplicate groups left, stop deduping
                if len(self.duplicates) < 1:
                    return self.stop_deduping()

                # Edge case: we remove the duplicate group at our current index entirely
                # and we are at the end of the list of duplicate groups
                if self.index >= len(self.duplicates):
                    self.index = len(self.duplicates) - 1

                # Edge case: we remove the duplicate group at index 0 but for some
                # reason decremented anyways
                if self.index < 0:
                    self.index = 0

                # reset current stuff, update ui
                self.current_duplicates = [FileItem(file_name)
                                           for file_name in self.duplicates[self.index]]
                self.current_image_index = 0
                self.photo = None
                self.banner_images = None
                self.load_images()
                self.display_image()
                self.update_dedupe_button_state()

                print_to_scrolltext(f"Removed images:\n {image_list_string}\n")

    @handle_exceptions
    def open_current_file(self):
        # Sanity checks
        if (not self.current_duplicates
            or (0 > self.current_image_index)
                or (self.current_image_index >= len(self.current_duplicates))):
            return

        file_path = os.path.join(
            self.dir, self.current_duplicates[self.current_image_index].file_name)

        if os.path.exists(file_path):
            try:
                # Windows
                if os.name == 'nt':
                    os.startfile(file_path)
                # macOS, Linux, etc.
                elif os.name == 'posix':
                    subprocess.call(["open", file_path])
                else:
                    print("Unsupported operating system.")
            except Exception as e:
                print(f"Error opening file: {e}")

    @handle_exceptions
    def convert_webp_to_png(self):
        thread_stdout = io.StringIO()
        log_handler = logging.StreamHandler(thread_stdout)
        logger = logging.getLogger()
        logger.addHandler(log_handler)

        webp_count = 0
        for root, _, files in os.walk(self.dir):
            for file in files:
                if file.lower().endswith('.webp'):
                    webp_count += 1
        print_to_scrolltext(f"Found {webp_count} images.")

        if webp_count < 1:
            return

        # Define paths for temp, webp, and png directories
        temp_dir = os.path.join(self.dir, 'temp')
        webp_dir = os.path.join(temp_dir, 'webp')

        # Create temp/webp and temp/png directories if they don't exist
        os.makedirs(webp_dir, exist_ok=True)

        webp_count = 0
        for root, _, files in os.walk(self.dir):
            for file in files:
                if file.lower().endswith('.webp'):
                    webp_count += 1
        print_to_scrolltext(f"Found {webp_count} images.")

        # Traverse the directory recursively and move all .webp files to temp/webp/
        for root, _, files in os.walk(self.dir):
            for file in files:
                if file.lower().endswith('.webp'):
                    webp_path = os.path.join(root, file)
                    target_webp_path = os.path.join(webp_dir, file)

                    # Move the .webp file to temp/webp/
                    shutil.move(webp_path, target_webp_path)
                    print_to_scrolltext(
                        f"Moved: {webp_path} -> {target_webp_path}")

        # Convert all .webp images in temp/webp/ to .png in temp/png/
        for webp_file in os.listdir(webp_dir):
            if webp_file.lower().endswith('.webp'):
                webp_path = os.path.join(webp_dir, webp_file)
                png_path = os.path.join(
                    temp_dir, os.path.splitext(webp_file)[0] + ".png")

                try:
                    # Open the .webp image and convert to .png
                    with Image.open(webp_path) as img:
                        img.save(png_path, "PNG")
                        print_to_scrolltext(
                            f"Converted: {webp_path} -> {png_path}")
                except Exception as e:
                    print_to_scrolltext(f"Failed to convert {webp_path}: {e}")

    @handle_exceptions
    def update_dedupe_button_state(self):
        resetUIState(self)

        updateHashButton(self)
        updateStartButton(self)
        updateStopButton(self)
        updateNextGroupButton(self)
        updatePrevGroupButton(self)
        updateGroupsLabel(self)
        updateNextImageButton(self)
        updatePrevImageButton(self)
        updateDeleteButton(self)
        updateOpenButton(self)
        updateKeepToggle(self)
        updateCurrentFileLabels(self)
        updateWEBPButton(self)


if __name__ == "__main__":
    root = tk.Tk()
    root.wm_state('zoomed')
    app = MainWindow(root)
    # allow the wrapper to access the tkinter app
    initialize(app)
    root.mainloop()
