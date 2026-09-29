from typing import List

class WorkflowEngine:
    def __init__(self, expected_sequence: List[str]):
        self.expected_sequence = expected_sequence
    
    def check_deviation(self, observed_sequence: List[str]) -> bool:
        """
        Compare the observed sequence with the expected workflow sequence.
        Returns True if a deviation is detected.
        """
        if not observed_sequence:
            return False
            
        # Basic sequence matching
        for i, observed in enumerate(observed_sequence):
            if i >= len(self.expected_sequence):
                return True # Extra steps observed
                
            if observed != self.expected_sequence[i] and observed != "Unknown":
                return True # Deviation
                
        return False
