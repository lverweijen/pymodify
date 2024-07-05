import dataclasses
import warnings
from typing import Collection, Callable, Any

import pandas as pd

from .primitives import Condition, FunctionCondition


@dataclasses.dataclass(slots=True)
class Check:
    condition: Condition | str | Callable[[Any], bool]
    name: str = None
    description: str = ""
    tags: Collection[str] = ()
    rewrite: bool = True

    def __post_init__(self):
        self.condition = Condition.make(self.condition, rewrite=self.rewrite)

        if isinstance(self.condition, FunctionCondition):
            condition = self.condition
            self.name = self.name or condition.name
            self.description = self.description or condition.description

        elif self.name is None:
            self.name = f"condition_{id(self)}"

    def __call__(self, *args, **kwargs):
        return self.condition(*args, **kwargs)

    def run(self, *args, **kwargs) -> "CheckResult":
        try:
            with warnings.catch_warnings(record=True) as wrn:
                result = self(*args, **kwargs)
            error = None
        except Exception as err:
            result = None
            error = err

        return CheckResult(check=self,
                           result=result,
                           error=error,
                           warnings=wrn)

    @property
    def fails(self):
        def invert(*args, **kwargs):
            return ~self(*args, **kwargs)

        invert.__name__ = self.name + ".fails"
        condition = FunctionCondition(invert)
        condition.parameters = self.condition.parameters
        return condition


class CheckResult:
    def __init__(self, check, result=None, error=None, warnings=()):
        self.check = check
        self.result = result
        self.error = error
        self.warnings = list(warnings)

        try:
            # Assume pd.Series
            self._value_counts = result.value_counts(dropna=False)
        except AttributeError:
            # Assume scalar
            if not error:
                self._value_counts = {result: 1}
            else:
                self._value_counts = {pd.NA: 1}

    def __repr__(self):
        output = ["<" + type(self).__name__,
                  "\n".join(f" {key}: {value}" for key, value in self.summary().items()),
                  ">"]
        return "\n".join(output)

    def summary(self):
        return {
            "name": str(self.check.name),
            "condition": str(self.check.condition),
            "items": self.items,
            "passes": self.passes,
            "fails": self.fails,
            "NAs": self.nas,
            "error": self.error,
            "warnings": len(self.warnings),
        }

    @property
    def items(self):
        try:
            return len(self.result)
        except TypeError:
            return 1

    @property
    def passes(self):
        return self._value_counts.get(True, 0)

    @property
    def fails(self):
        return self._value_counts.get(False, 0)

    @property
    def nas(self):
        return self._value_counts.get(pd.NA, 0)

    @property
    def has_error(self):
        return self.error is not None


class CheckReport(Collection[CheckResult]):
    def __init__(self, check_results, index=None):
        self.check_results = check_results
        self.index = index

    def __contains__(self, item):
        return item in self

    def __iter__(self):
        return iter(self.check_results)

    def __len__(self):
        return len(self.check_results)

    def summary(self):
        return pd.DataFrame([res.summary() for res in self])

    def dataframe(self):
        return pd.DataFrame({
            res.check.name: res.result for res in self
        }, index=self.index)


def run_checks(data, checklist):
    results = []
    for check in checklist:
        results.append(check.run(data))
    return CheckReport(results, index=getattr(data, "index", None))