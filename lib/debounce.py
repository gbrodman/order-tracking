# Taken from https://gist.github.com/walkermatt/2871026

from threading import Timer


def debounce(wait):

  def decorator(fn):

    def debounced(*args, **kwargs):

      def call_it():
        fn(*args, **kwargs)

      try:
        debounced.t.cancel()
      except AttributeError:
        pass
      debounced.t = Timer(wait, call_it)
      debounced.t.start()

    return debounced

  return decorator
