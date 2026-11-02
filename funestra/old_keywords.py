from functools import wraps


def still_answer_to(cls, **new_by_old):
    original = cls.__init__

    @wraps(original)
    def init(self, *args, **kwargs):
        for old, new in new_by_old.items():
            if old in kwargs:
                kwargs[new] = kwargs.pop(old)
        original(self, *args, **kwargs)

    cls.__init__ = init
    for old, new in new_by_old.items():
        setattr(cls, old, property(lambda self, name=new: getattr(self, name)))
    return cls
