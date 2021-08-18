# try:
#     import tensorflow as tf
#     tf.compat.v1.disable_eager_execution() # TODO: write new Logger class for TensorFlow v2

#     class Logger(object):
#         def __init__(self, log_dir):
#             """Create a summary writer logging to log_dir."""
#             self.writer = tf.compat.v1.summary.FileWriter(log_dir)

#         def scalar_summary(self, tag, value, step):
#             """Log a scalar variable."""
#             summary = tf.compat.v1.Summary(
#                 value=[tf.compat.v1.Summary.Value(tag=tag, simple_value=value)])
#             self.writer.add_summary(summary, step)

#         def list_of_scalars_summary(self, tag_value_pairs, step):
#             """Log scalar variables."""
#             summary = tf.compat.v1.Summary(value=[tf.compat.v1.Summary.Value(
#                 tag=tag, simple_value=value) for tag, value in tag_value_pairs])
#             self.writer.add_summary(summary, step)
# except:
#     class Logger(object):
#         def __init__(self, log_dir):
#             pass

import tensorflow as tf
tf.compat.v1.disable_eager_execution() # TODO: write new Logger class for TensorFlow v2

class Logger(object):
    def __init__(self, log_dir):
        """Create a summary writer logging to log_dir."""
        self.writer = tf.compat.v1.summary.FileWriter(log_dir)

    def scalar_summary(self, tag, value, step):
        """Log a scalar variable."""
        summary = tf.compat.v1.Summary(
            value=[tf.compat.v1.Summary.Value(tag=tag, simple_value=value)])
        self.writer.add_summary(summary, step)

    def list_of_scalars_summary(self, tag_value_pairs, step):
        """Log scalar variables."""
        summary = tf.compat.v1.Summary(value=[tf.compat.v1.Summary.Value(
            tag=tag, simple_value=value) for tag, value in tag_value_pairs])
        self.writer.add_summary(summary, step)

class DummyLogger:
    def __init__(self, log_dir):
        pass

    def scalar_summary(self, tag, value, step):
        pass

    def list_of_scalars_summary(self, tag_value_pairs, step):
        pass

