"""节点基类 —— 单一职责:LangGraph 节点的统一接口。

所有入库与查询节点继承 BaseNode,实现 name 类属性 + process(state) 抽象方法;
基类 __call__ 统一封装日志、异常包装(包装成 IngestProcessError 或 QueryProcessError),
让 LangGraph 调度层无脑调用。

日志前缀区分两条业务流:
- 入库图节点 → "ingest.<name>"
- 查询图节点 → "query.<name>"

同步/异步支持:
- 基类 __call__ 统一是协程函数(async def)。LangGraph 判定节点是否异步靠
  inspect.iscoroutinefunction(节点实例的 __call__),故 __call__ 必须是协程,否则
  异步节点(web_search / xhs_search)的协程不会被 await,报「Expected dict, got coroutine」。
- 内部分流:子类 process 是 async def → 直接 await;是 sync def → asyncio.to_thread 丢线程池
  (避免阻塞事件循环,与 LangGraph 对同步节点 to_thread 的语义一致)。

异常设计:
- 业务异常(自定义 IngestProcessError / QueryProcessError)由 __call__ 抛出后,LangGraph
  立即停止图执行,不返回半成品状态;
- 任意节点内未捕获异常都会被 __call__ 包装,保留原始栈信息供排查。
"""
from __future__ import annotations

import inspect
import logging
import asyncio
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

    async def __call__(self, state: T) -> T:
        """LangGraph 节点调用入口:统一协程。

        为什么 __call__ 必须是协程函数(async def):
        LangGraph 判定节点是否异步靠 inspect.iscoroutinefunction(节点实例的 __call__),
        不是看它「返回什么」。若 __call__ 是同步 def 而内部 return 一个未 await 的协程,
        LangGraph 会把它当成同步节点,在 ainvoke / astream 里拿到裸协程对象当返回值,
        触发 InvalidUpdateError:「Expected dict, got <coroutine object ...>」。
        web_search / xhs_search 等 async 节点都会踩中这个坑,故基类统一按协程注册。

        内部分流:
        - 异步 process(async def):直接 await(保持原生异步,不丢线程池);
        - 同步 process(sync def):asyncio.to_thread 丢线程池,避免阻塞事件循环
          (与 LangGraph 对同步节点 to_thread 的既有语义一致)。
        两者都统一打日志 + 包异常(包成 IngestProcessError / QueryProcessError)。
        """
        self.logger.info(f"--- {self.name} 开始 ---")
        try:
            if inspect.iscoroutinefunction(self.process):
                result = await self.process(state)
            else:
                result = await asyncio.to_thread(self.process, state)
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
