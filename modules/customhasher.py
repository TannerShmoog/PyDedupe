from imagededup.methods import PHash
from imagededup.utils.image_utils import preprocess_image, check_image_array_hash
from imagededup.utils.logger import return_logger
from imagededup.utils.general_utils import (
    parallelise,
    generate_files,
    generate_relative_names
)
from typing import Optional
from functools import partial
import numpy as np
from pathlib import Path
import cv2
import os
from modules.constants import *

logger = return_logger(__name__)


class VideoAwarePHash(PHash):
    def encode_image(
        self, image_file=None,
        image_array: Optional[np.ndarray] = None,
        use_first_frame: bool = None,
        use_last_frame: bool = None,
        frame_timestamp_seconds: int = None
    ) -> str:
        try:
            if image_file and os.path.exists(image_file):
                image_file = Path(image_file)
                if image_file.suffix.lower() in VIDEO_FORMATS:
                    if use_first_frame:
                        image_array = self.extract_first_frame(image_file)
                    elif use_last_frame:
                        image_array = self.extract_last_frame(image_file)
                    elif frame_timestamp_seconds is not None:
                        image_array = self.extract_specific_frame(
                            image_file, frame_timestamp_seconds)
                    else:
                        raise ValueError(
                            "No valid frame selection specified for video.")

                    if image_array is None:
                        # Hacky way to prevent crash when a video file read failed for whatever reason, guarantees no dupes.
                        return ""

                    # Do sanity checks on array
                    check_image_array_hash(image_array)
                    image_pp = preprocess_image(
                        image=image_array, target_size=self.target_size, grayscale=True
                    )
                else:
                    # Use the original PHash's logic for regular images
                    return super().encode_image(image_file=image_file)
            elif isinstance(image_array, np.ndarray):
                # Use the original PHash's logic for image arrays
                return super().encode_image(image_array=image_array)
            else:
                raise ValueError
        except (ValueError, TypeError):
            raise ValueError(
                'Please provide either image file path or image array!')

        return self._hash_func(image_pp) if isinstance(image_pp, np.ndarray) else None

    def extract_first_frame(self, video_file):
        cap = None
        try:
            cap = cv2.VideoCapture(str(video_file))
            if cap.isOpened():
                success, frame = cap.read()
                if success:
                    return frame
            return None
        finally:
            if cap:
                cap.release()

    def extract_last_frame(self, video_file):
        cap = None
        try:
            cap = cv2.VideoCapture(str(video_file))
            if cap.isOpened():
                cap.set(cv2.CAP_PROP_POS_FRAMES, cap.get(
                    cv2.CAP_PROP_FRAME_COUNT) - 1)
                success, last_frame = cap.read()
                if not success:
                    # Reset to start of video
                    cap.set(cv2.CAP_PROP_POS_FRAMES, 0)
                    last_frame = None
                    while True:
                        success, frame = cap.read()
                        if not success:
                            break
                        last_frame = frame
                if last_frame is not None:
                    return last_frame
            return None
        finally:
            if cap:
                cap.release()

    def extract_specific_frame(self, video_file, seconds):
        cap = None
        try:
            cap = cv2.VideoCapture(str(video_file))
            fps = cap.get(cv2.CAP_PROP_FPS)
            if cap.isOpened():
                cap.set(cv2.CAP_PROP_POS_FRAMES, seconds * fps)
                success, frame = cap.read()
                if success:
                    return frame
            return None
        finally:
            if cap:
                cap.release()

    def encode_images(
        self, image_dir=None, recursive=False,
        use_first_frame: bool = None,
        use_last_frame: bool = None,
        frame_timestamp_seconds: int = None
    ):
        if not os.path.isdir(image_dir):
            raise ValueError('Please provide a valid directory path!')

        files = generate_files(image_dir, recursive)

        logger.info(f'Start: Calculating hashes...')

        # Filter the files in the directory for
        if any([use_first_frame, use_last_frame, frame_timestamp_seconds is not None]):
            # Video-specific processing
            files = [f for f in files if f.suffix.lower() in VIDEO_FORMATS]
        else:
            # Process images directly
            files = [f for f in files if f.suffix.lower() not in VIDEO_FORMATS]

        # Generate a partial function to use kwargs
        # Avoids having to redefine parallelise
        partial_encode_image = partial(
            self.encode_image,
            use_first_frame=use_first_frame,
            use_last_frame=use_last_frame,
            frame_timestamp_seconds=frame_timestamp_seconds
        )
        hashes = parallelise(
            partial_encode_image, files, self.verbose
        )

        hash_initial_dict = dict(
            zip(generate_relative_names(image_dir, files), hashes))
        hash_dict = {
            k: v for k, v in hash_initial_dict.items() if v
        }  # To ignore None (returned if some problem with image file)

        logger.info(f'End: Calculating hashes!')
        return hash_dict
