import yaml


__metadata__ = type


class FeatureFlags:
    def __init__(self, config_obj):
        self._flags = config_obj if config_obj is not None else {}

    def is_enabled(self, feature):
        return self._flags.get(feature, False)

    def is_disabled(self, feature):
        return not self.is_enabled(feature)

    @property
    def flags(self):
        return self._flags

    @classmethod
    def from_config(cls, config_path):
        with open(config_path) as f:
            return cls(yaml.safe_load(f))
