class FileItem:
    # Stores information about items in self.current_duplicates
    def __init__(self, file_name):
        self.file_name = file_name
        self.image = None
        self.banner_label = None
        self.should_keep = True
        self.dims_string = ""
        self.length_string = ""
