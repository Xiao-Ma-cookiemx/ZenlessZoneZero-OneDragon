import time
from concurrent.futures import ThreadPoolExecutor, Future

import cv2
import threading
from cv2.typing import MatLike
from typing import List, Optional, Union

from one_dragon.base.screen.screen_area import ScreenArea
from one_dragon.utils import cv2_utils, thread_utils, cal_utils, os_utils
from one_dragon.utils.log_utils import log
from zzz_od.context.zzz_context import ZContext
from zzz_od.game_data.agent import Agent, AgentEnum
from zzz_od.hollow_zero.hollow_level_info import HollowLevelInfo
from zzz_od.hollow_zero.hollow_map import hollow_map_utils
from zzz_od.hollow_zero.hollow_map.hollow_zero_map import HollowZeroMap, HollowZeroMapNode
from zzz_od.hollow_zero.hollow_zero_data_service import HallowZeroDataService
from zzz_od.yolo.hollow_event_detector import HollowEventDetector

_hollow_context_executor = ThreadPoolExecutor(thread_name_prefix='od_hollow_context', max_workers=16)


class HollowContext:

    def __init__(self, ctx: ZContext):
        self.ctx: ZContext = ctx
        self.agent_list: Optional[List[Agent]] = None

        self.data_service: HallowZeroDataService = HallowZeroDataService()
        self.level_info: HollowLevelInfo = HollowLevelInfo()

        self._event_model: Optional[HollowEventDetector] = None

        self.map_results: List[HollowZeroMap] = []  # 识别的地图结果

    def check_agent_list(self, screen: MatLike) -> Optional[List[Agent]]:
        """
        识别空洞画面里的角色列表
        """
        check_agent_area = [
            self.ctx.screen_loader.get_area('零号空洞-事件', ('角色-%d' % i))
            for i in range(1, 4)
        ]
        area_img = [
            cv2_utils.crop_image_only(screen, i.rect)
            for i in check_agent_area
        ]

        result_agent_list: List[Optional[Agent]] = []
        future_list: List[Future] = []

        for img in area_img:
            future_list.append(_hollow_context_executor.submit(self._match_agent_in, img, self.agent_list))

        any_not_none: bool = False
        for future in future_list:
            try:
                result = future.result()
                result_agent_list.append(result)
                if result is not None:
                    any_not_none = True
            except Exception:
                log.error('识别角色头像失败', exc_info=True)
                result_agent_list.append(None)

        if not any_not_none:
            return None
        self.agent_list = result_agent_list
        return self.agent_list

    def _match_agent_in(self, img: MatLike, possible_agents: Optional[List[Agent]] = None) -> Optional[Agent]:
        """
        在候选列表重匹配角色 TODO 待优化
        :return:
        """
        prefix = 'avatar_'
        if possible_agents is None:
            possible_agents = [agent_enum.value for agent_enum in AgentEnum]
        for agent in possible_agents:
            mrl = self.ctx.tm.match_template(img, 'hollow', prefix + agent.agent_id, threshold=0.8)
            if mrl.max is not None:
                return agent

        return None

    def check_battle_screen(self, screen: MatLike, screenshot_time: float,
                            check_battle_end: bool = True,
                            sync: bool = False) -> None:
        """
        异步判断角战斗画面
        :return:
        """
        future_list: List[Future] = []

        if check_battle_end:
            future_list.append(_hollow_context_executor.submit(self._check_battle_end, screen, screenshot_time))

        for future in future_list:
            future.add_done_callback(thread_utils.handle_future_result)

        if sync:
            for future in future_list:
                future.result()

    def _check_battle_end(self, screen: MatLike, screenshot_time: float) -> None:
        if not self._check_end_lock.acquire(blocking=False):
            return

        try:
            if screenshot_time - self._last_check_end_time < cal_utils.random_in_range(self._check_end_interval):
                # 还没有达到识别间隔
                return
            self._last_check_end_time = screenshot_time

        except Exception:
            log.error('识别战斗结束失败', exc_info=True)
        finally:
            self._check_end_lock.release()

    def init_event_yolo(self, use_gpu: bool = False) -> None:
        if self._event_model is None or self._event_model.gpu != use_gpu:
            self._event_model = HollowEventDetector(
                model_parent_dir_path=os_utils.get_path_under_work_dir('assets', 'models', 'yolo'),
                gpu=use_gpu,
            )

    def clear_detect_history(self) -> None:
        """
        清除识别记录
        :return:
        """
        if self._event_model is None:
            return
        self._event_model.run_result_history.clear()

    def check_current_map(self, screen: MatLike, screenshot_time: float) -> Optional[HollowZeroMap]:
        if self._event_model is None:
            return None
        result = self._event_model.run(screen, run_time=screenshot_time)
        # from zzz_od.yolo import detect_utils
        # cv2_utils.show_image(detect_utils.draw_detections(result), wait=0)
        if result is None:
            return None

        current_map = hollow_map_utils.construct_map_from_yolo_result(result, self.data_service.name_2_entry)
        if current_map.current_idx is None and self.ctx.env_config.is_debug:
            from one_dragon.utils import debug_utils
            # file_name = debug_utils.save_debug_image(screen, prefix='map_detect_fail')

        self.map_results.append(current_map)
        while len(self.map_results) > 0 and screenshot_time - self.map_results[0].check_time > 2:
            self.map_results.pop(0)

        merge_map = hollow_map_utils.merge_map(self.map_results)
        if self.ctx.env_config.is_debug:
            result_img = hollow_map_utils.draw_map(screen, merge_map)
            cv2_utils.show_image(result_img)

        return merge_map

    def check_before_move(self, screen: MatLike) -> None:
        """
        移动前 进行识别
        :param screen:
        :return:
        """
        if self.agent_list is None:
            self.check_agent_list(screen)

    def get_next_to_move(self, current_map: HollowZeroMap) -> Optional[HollowZeroMapNode]:
        """
        获取下一步的移动方向
        :param current_map:
        :return:
        """
        idx_2_route = hollow_map_utils.search_map(current_map)

        # 1步可到的奖励 都先领取了
        route = hollow_map_utils.get_route_in_1_step_benefit(idx_2_route)
        if route is not None:
            return current_map.nodes[route.first_step]

        # 队员不满的时候 优先去增援
        if self.ctx.hollow.agent_list is None or len(self.ctx.hollow.agent_list) < 3:
            route = hollow_map_utils.get_route_by_entry(idx_2_route, '呼叫增援')
            if route is not None:
                return current_map.nodes[route.first_step]

        # 有业绩的时候 去拿业绩
        route = hollow_map_utils.get_route_by_entry(idx_2_route, '业绩考察点')
        if route is not None:
            return current_map.nodes[route.first_step]

        # 有银行的时候 去银行
        route = hollow_map_utils.get_route_by_entry(idx_2_route, '零号银行')
        if route is not None:
            return current_map.nodes[route.first_step]

        # 有出口的时候 去出口
        route = hollow_map_utils.get_route_by_entry(idx_2_route, '守门人')
        if route is not None:
            return current_map.nodes[route.first_step]

        # 没有特殊点的时候 按副本类型走特定方向
        if self.level_info.level == 2:  # 第2层往上走
            route = hollow_map_utils.get_route_by_direction(idx_2_route, 'w')
            if route is not None:
                return current_map.nodes[route.first_step]

        return None

    def update_context_after_move(self, node: HollowZeroMapNode) -> None:
        """
        点击后 更新
        :param node:
        :return:
        """
        pass


def __debug_draw_detect():
    ctx = ZContext()
    ctx.init_by_config()

    from one_dragon.utils import debug_utils
    img = debug_utils.get_debug_image('event_1')

    ctx.hollow.init_event_yolo()
    result = ctx.hollow._event_model.run(img)
    from zzz_od.yolo import detect_utils
    result_img = detect_utils.draw_detections(result)
    cv2_utils.show_image(result_img, wait=0)
    cv2.destroyAllWindows()


def __debug_get_map():
    ctx = ZContext()
    ctx.init_by_config()

    from one_dragon.utils import debug_utils
    img_list = [
        '_1723649519504',
    ]
    for i in img_list:
        img = debug_utils.get_debug_image(i)

        ctx.hollow.init_event_yolo(False)
        current_map = ctx.hollow.check_current_map(img, time.time())

    print(current_map.current_idx)
    target = ctx.hollow.get_next_to_move(current_map)
    result_img = hollow_map_utils.draw_map(img, current_map, next_node=target)
    cv2_utils.show_image(result_img, wait=0)
    cv2.destroyAllWindows()


if __name__ == '__main__':
    __debug_get_map()

