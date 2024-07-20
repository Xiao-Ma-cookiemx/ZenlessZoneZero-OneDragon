from typing import List, Callable

from one_dragon.base.conditional_operation.atomic_op import AtomicOp
from one_dragon.base.conditional_operation.state_handler import StateHandler, construct_state_handler
from one_dragon.base.conditional_operation.state_recorder import StateRecorder


class SceneHandler:

    def __init__(self, interval_seconds: float, state_handlers: List[StateHandler]):
        self.interval_seconds: float = interval_seconds
        self.state_handlers: List[StateHandler] = state_handlers
        self.last_trigger_time: float = 0

    def execute(self, now: float) -> None:
        """
        按优先级判断状态 找到需要执行的执行并执行
        :param now:
        :return:
        """
        if now - self.last_trigger_time <= self.interval_seconds:
            return
        self.last_trigger_time = now
        for sh in self.state_handlers:
            if sh.check_and_run(now):
                return

    def stop_running(self) -> None:
        """
        停止运行
        :return:
        """
        for sh in self.state_handlers:
            sh.stop_running()

    def dispose(self) -> None:
        """
        销毁
        :return:
        """
        if self.state_handlers is not None:
            for handler in self.state_handlers:
                handler.dispose()


def construct_scene_handler(
        scene_data: dict,
        state_recorders: List[StateRecorder],
        op_constructor: Callable[[str, List[str]], AtomicOp]
):
    interval_seconds = scene_data.get('interval', 0.5)

    state_handlers: List[StateHandler] = []
    data_handlers = scene_data.get('handlers', [])
    for state_data in data_handlers:
        state_handlers.append(construct_state_handler(state_data, state_recorders, op_constructor))

    return SceneHandler(interval_seconds, state_handlers)
