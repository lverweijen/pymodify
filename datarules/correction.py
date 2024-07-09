import dataclasses
import traceback

import pandas as pd

from .primitives import Condition, FunctionAction, Action
from .check import Check
from .rule import RuleResult, Rule


@dataclasses.dataclass(slots=True)
class Correction(Rule):
    action: Action
    trigger: Condition

    @classmethod
    def from_dict(cls, data):
        # Renames
        if "if" in data:
            data["trigger"] = data.pop("if")
        if "then" in data:
            data["action"] = data.pop("then")

        return cls(**data)

    def __post_init__(self):
        if isinstance(self.trigger, Check):
            raise ValueError("Check can not be used as a condition, but `check.fails` can.")

        self.trigger = Condition.make(self.trigger)
        self.action = Action.make(self.action)

        if isinstance(self.action, FunctionAction):
            action = self.action
            self.name = self.name or action.name
            self.description = self.description or action.description

        self._rule_init()

    def __call__(self, *args, **kwargs):
        return self.action(*args, **kwargs)

    def run(self, data):
        is_applicable = None
        error = None

        try:
            is_applicable = self.trigger(data)  # Also handle true/false
            result = self.action(data)
        except Exception as err:
            error = err
            traceback.print_exc()
        else:
            if isinstance(is_applicable, bool):
                is_applicable = pd.Series(is_applicable, index=data.index)

            for k, v in result.items():
                data.loc[is_applicable, k] = v

        return CorrectionResult(correction=self,
                                applied=is_applicable,
                                error=error,
                                warnings=())


class CorrectionResult(RuleResult):
    fields = ["name", "trigger", "action", "applied", "error", "warnings"]

    def __init__(self, correction, applied, error=None, warnings=()):
        self.correction = correction
        self.applied = applied
        self.error = error
        self.warnings = list(warnings)

    def __repr__(self):
        output = ["<" + type(self).__name__,
                  "\n".join(f" {key}: {value}" for key, value in self.summary().items()),
                  ">"]
        return "\n".join(output)

    def summary(self):
        count_applied = self.applied.astype(bool).sum()

        return {
            "name": str(self.correction.name),
            "trigger": str(self.correction.trigger),
            "action": str(self.correction.action),
            "applied": count_applied,
            "error": self.error,
            "warnings": len(self.warnings),
        }

    @property
    def has_error(self):
        return self.error is not None