from typing import List

from one_dragon.base.conditional_operation.atomic_op import AtomicOp
from one_dragon.base.conditional_operation.state_recorder import StateRecorder
from zzz_od.auto_battle.atomic_op.dodge import AtomicDodge
from zzz_od.auto_battle.atomic_op.switch_next import AtomicSwitchNext
from zzz_od.auto_battle.atomic_op.switch_prev import AtomicSwitchPrev
from zzz_od.auto_battle.atomic_op.wait import AtomicWait
from zzz_od.context.battle_context import BattleEventEnum
from zzz_od.context.yolo_context import YoloStateEventEnum
from zzz_od.context.zzz_context import ZContext


class AutoBattleLoader:

    def __init__(self, ctx: ZContext):
        self.ctx: ZContext = ctx

    def get_all_state_recorders(self) -> List[StateRecorder]:
        """
        获取所有的状态记录器
        :return:
        """
        return [
            StateRecorder(self.ctx, YoloStateEventEnum.DODGE_YELLOW.value),
            StateRecorder(self.ctx, YoloStateEventEnum.DODGE_RED.value),
            StateRecorder(self.ctx, BattleEventEnum.BTN_DODGE.value),
            StateRecorder(self.ctx, BattleEventEnum.BTN_SWITCH_NEXT.value),
            StateRecorder(self.ctx, BattleEventEnum.BTN_SWITCH_PREV.value),
        ]

    def get_atomic_op(self, op_name: str, op_data: List[str]) -> AtomicOp:
        """
        获取一个原子操作
        :param op_name:
        :param op_data:
        :return:
        """
        if op_name == AtomicDodge.OP_NAME:
            return AtomicDodge(self.ctx)
        elif op_name == AtomicSwitchNext.OP_NAME:
            return AtomicSwitchNext(self.ctx)
        elif op_name == AtomicSwitchPrev.OP_NAME:
            return AtomicSwitchPrev(self.ctx)
        elif op_name == AtomicWait.OP_NAME:
            return AtomicWait(float(op_data[0]))
        else:
            raise ValueError('非法的指令 %s' % op_name)