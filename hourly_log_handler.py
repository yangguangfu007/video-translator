import os
import time
import logging
from datetime import datetime

class HourlyRotatingFileHandler(logging.FileHandler):
    """
    A handler that rotates log files on an hourly basis.
    """
    def __init__(self, log_dir, prefix='app', suffix='.log', encoding='utf-8'):
        self.log_dir = log_dir
        self.prefix = prefix
        self.suffix = suffix
        self.encoding = encoding
        self.current_hour = self._get_current_hour()
        
        # Create the log directory if it doesn't exist
        os.makedirs(self.log_dir, exist_ok=True)
        
        # Generate the current log filename
        filename = self._get_log_filename()
        
        # Initialize the FileHandler with the current log file
        super().__init__(filename, encoding=encoding)
    
    def _get_current_hour(self):
        """Get the current hour as a string in format YYYY-MM-DD_HH"""
        return datetime.now().strftime('%Y-%m-%d_%H')
    
    def _get_log_filename(self):
        """Generate the log filename based on the current hour"""
        return os.path.join(self.log_dir, f"{self.prefix}_{self.current_hour}{self.suffix}")
    
    def emit(self, record):
        """
        Emit a record, rotating the file if the hour has changed.
        """
        # Check if we need to rotate to a new file
        current_hour = self._get_current_hour()
        if current_hour != self.current_hour:
            # Hour has changed, switch to a new file
            self.current_hour = current_hour
            
            # Close the current file
            self.close()
            
            # Open a new file
            self.baseFilename = self._get_log_filename()
            self._open()
        
        # Emit the record
        super().emit(record)
