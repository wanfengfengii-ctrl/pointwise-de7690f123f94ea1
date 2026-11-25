from dataclasses import dataclass


@dataclass(frozen=True)
class OutletOutcome:
    outlet: str
    hops: int

    def __post_init__(self):
        if not isinstance(self.outlet, str) or not self.outlet:
            raise ValueError('outlet name required')
        if type(self.hops) is not int or self.hops < 0:
            raise ValueError('outlet hops must be a nonnegative integer')

    def as_record(self):
        return {'kind': 'outlet', 'outlet': self.outlet, 'hops': self.hops}


@dataclass(frozen=True)
class LoopOutcome:
    entry_hops: int
    loop_length: int

    def __post_init__(self):
        if type(self.entry_hops) is not int or self.entry_hops < 0:
            raise ValueError('loop entry must be a nonnegative integer')
        if type(self.loop_length) is not int or self.loop_length <= 0:
            raise ValueError('loop length must be a positive integer')

    def as_record(self):
        return {'kind': 'loop', 'entry_hops': self.entry_hops, 'loop_length': self.loop_length}
