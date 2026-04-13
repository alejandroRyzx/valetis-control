from config import TOTAL_SPACES


class ParkingManager:
    def __init__(self, db):
        self.db = db
        self.total_spaces = TOTAL_SPACES
        self.spaces = [None] * TOTAL_SPACES
        self._load_occupied_spaces()

    def _load_occupied_spaces(self):
        tickets = self.db.get_all_tickets()
        for ticket in tickets:
            if ticket["spot"] is not None and not ticket["used"]:
                self.spaces[ticket["spot"]] = ticket["code"]

    def available_spaces(self):
        return sum(1 for s in self.spaces if s is None)

    def is_full(self):
        return self.available_spaces() == 0

    def occupy_space(self, spot_index: int, ticket_code: str):
        if 0 <= spot_index < self.total_spaces and self.spaces[spot_index] is None:
            self.spaces[spot_index] = ticket_code
            return True
        return False

    def free_space_by_ticket(self, ticket_code: str):
        for i, code in enumerate(self.spaces):
            if code == ticket_code:
                self.spaces[i] = None
                return i
        return None