"""Curate the most important info for one feature (see package docstring for the block shapes).

def curate(event: Event, *, now: datetime, busy: float | None) -> dict
    - venue with upcoming ticketed events  -> posters block first
    - open pitch                           -> pitch block (which pitches, open today?)
    - park                                 -> "picnics happening now" from public invites nearby
    - nightclub                            -> live busy-now block
    - any event                            -> facts (when / where) + social (going / wants company)
TODO(backend)
"""
