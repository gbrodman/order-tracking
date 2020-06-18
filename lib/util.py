import sys
import traceback


def get_traceback_lines() -> str:
  """
  Call this from inside an except statement to get the full stack trace formatted
  as a newline-delimited String, i.e. to use for outputting in cases where you
  want to swallow the Exception instead of rethrowing.
  """
  exc_type, value, trace = sys.exc_info()
  formatted_trace = traceback.format_tb(trace)
  lines = [str(exc_type), str(value)] + formatted_trace
  return "\n".join(lines)


def chunks(lst, n):
  """Yield successive n-sized chunks from lst."""
  for i in range(0, len(lst), n):
    yield lst[i:i + n]
