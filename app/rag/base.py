"""节点基类 —— 单一职责:LangGraph 节点的统一接口。

所有入库与查询节点继承 BaseNode,实现 name 类属性 + process(state) 抽象方法;
基类 __call__ 统一封装日志、异常包装(包装成 IngestProcessError 或 QueryProcessError),
让 LangGraph 调度层无脑调用。

日志前缀区分两条业务流:
- 入库图节点 → "ingest.<name>"
- 查询图节点 → "query.<name>"

同步/异步支持:
- 默认 process 是同步函数;基类按同步路径包装。
- 若子类的 process 是协程函数(async def),基类返回一个「可被 LangGraph await 的协程」,
  内部仍走日志 + 异常包装。LangGraph 对 sync/async node 都原生支持。

异常设计:
- 业务异常(自定义 IngestProcessError / QueryProcessError)由 __call__ 抛出后,LangGraph
  立即停止图执行,不返回半成品状态;
- 任意节点内未捕获异常都会被 __call__ 包装,保留原始栈信息供排查。
"""
from __future__ import annotations

import inspect
import logging
from abc import ABC, abstractmethod
from typing import Generic, TypeVar

T = TypeVar("T")  # 泛型状态类型:入库图 / 查询图各自 TypedDict


class NodeProcessError(RuntimeError):
    """节点执行失败的统一基类。"""

    def __init__(self, message: str, node_name: str, cause: BaseException | None = None):
        super().__init__(message)
        self.node_name = node_name
        self.cause = cause


class IngestProcessError(NodeProcessError):
    """入库图节点失败。"""


class QueryProcessError(NodeProcessError):
    """查询图节点失败。"""


class BaseNode(ABC, Generic[T]):
    """LangGraph 节点基类。

    用法:
        class NodePreprocess(BaseNode):
            name = "preprocess"
            flow = "query"

            def __init__(self):
                super().__init__()
                self._llm = LLMClient(role="fast")

            def process(self, state: QueryGraphState) -> QueryGraphState:
                state["rewritten_query"] = self._rewrite(state["original_query"])
                return state

        # 异步节点(Web 搜索需 await MCP stdio):
        class NodeWebSearch(BaseNode):
            name = "web_search"
            flow = "query"

            async def process(self, state): ...

        # graph 装配:
        wf.add_node("preprocess", NodePreprocess())
    """

    name: str = "base_node"
    flow: str = "base"  # 子类覆盖:"ingest" 或 "query"

    def __init__(self):
        self.logger = logging.getLogger(f"{self.flow}.{self.name}")

    def __call__(self, state: T):
        """LangGraph 节点调用入口:同步 process 走同步包装,async process 返回协程。

        LangGraph 对 sync/async node 都原生支持:返回值是 dict 走同步;返回协程则被 await。
        """
        if inspect.iscoroutinefunction(self.process):
            return self._acall(state)
        try:
            self.logger.info(f"--- {self.name} 开始 ---")
            result = self.process(state)
            self.logger.info(f"--- {self.name} 完成 ---")
            return result
        except NodeProcessError:
            raise
        except Exception as e:
            self.logger.error(f"{self.name} 失败: {e}")
            cls = IngestProcessError if self.flow == "ingest" else QueryProcessError
            raise cls(str(e), self.name, cause=e) from e

    async def _acall(self, state: T) -> T:
        """异步 process 的包装路径。"""
        try:
            self.logger.info(f"--- {self.name} 开始 ---")
            result = await self.process(state)
            self.logger.info(f"--- {self.name} 完成 ---")
            return result
        except NodeProcessError:
            raise
        except Exception as e:
            self.logger.error(f"{self.name} 失败: {e}")
            cls = IngestProcessError if self.flow == "ingest" else QueryProcessError
            raise cls(str(e), self.name, cause=e) from e

    @abstractmethod
    def process(self, state: T):
        """子类实现具体逻辑。返回更新后的状态(同步返回 dict;async 返回协程)。"""
        raise NotImplementedError
