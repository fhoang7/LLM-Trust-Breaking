"""Failure-mode tests for QueuedOpenRouterClient, run against a local scripted server.

Each test queues the HTTP responses the "server" should return, so no network or API key is needed.

Run from the repo root:  python -m unittest tests.test_queued_openrouter_failures -v
"""
import contextlib
import io
import unittest

from aiohttp import web

from src.llm.providers.queued_openrouter import QueuedOpenRouterClient


def ok_body(content, finish_reason="stop"):
    return {"choices": [{"finish_reason": finish_reason,
                         "message": {"role": "assistant", "content": content}}]}


class ScriptedServerCase(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.script = []      # list of (status, json_body, headers)
        self.seen = []        # request json bodies, in arrival order

        async def handler(request):
            self.seen.append(await request.json())
            status, body, headers = self.script.pop(0)
            return web.json_response(body, status=status, headers=headers)

        app = web.Application()
        app.router.add_post("/v1/chat/completions", handler)
        self.runner = web.AppRunner(app)
        await self.runner.setup()
        site = web.TCPSite(self.runner, "127.0.0.1", 0)
        await site.start()
        port = self.runner.addresses[0][1]

        self.client = QueuedOpenRouterClient(api_key="test", max_workers=1, max_retries=3)
        self.client.base_url = f"http://127.0.0.1:{port}/v1/chat/completions"
        self.client.RETRY_BASE_SECONDS = 0.01

    async def asyncTearDown(self):
        await self.runner.cleanup()

    def request(self, cid="c1", max_tokens=100):
        return {"custom_id": cid, "model": "m/x", "max_tokens": max_tokens,
                "messages": [{"role": "user", "content": "hi"}]}

    async def run_one(self, **kw):
        results = await self.client._execute_all_async([self.request(**kw)])
        return results["c1"]


class RateLimitTests(ScriptedServerCase):
    async def test_429_is_retried_and_then_succeeds(self):
        self.script = [(429, {"error": "slow down"}, {}),
                       (429, {"error": "slow down"}, {"Retry-After": "0"}),
                       (200, ok_body('{"choice": "CHEAP"}'), {})]
        self.assertEqual(await self.run_one(), {"choice": "CHEAP"})
        self.assertEqual(len(self.seen), 3)

    async def test_persistent_429_reports_status_after_max_retries(self):
        self.script = [(429, {"error": "slow down"}, {})] * 3
        res = await self.run_one()
        self.assertEqual(res["status"], "error")
        self.assertIn("429", res["error"])
        self.assertEqual(len(self.seen), 3)

    async def test_non_retryable_status_is_not_retried(self):
        self.script = [(401, {"error": "bad key"}, {})]
        res = await self.run_one()
        self.assertEqual(res["status"], "error")
        self.assertIn("401", res["error"])
        self.assertEqual(len(self.seen), 1)


class EmptyContentTests(ScriptedServerCase):
    async def test_truncated_empty_content_is_retried_with_larger_budget(self):
        self.script = [(200, ok_body(None, "length"), {}),
                       (200, ok_body('{"choice": "CHEAP"}'), {})]
        self.assertEqual(await self.run_one(max_tokens=2000), {"choice": "CHEAP"})
        self.assertEqual([b["max_tokens"] for b in self.seen], [2000, 6000])

    async def test_truncated_twice_reports_finish_reason(self):
        self.script = [(200, ok_body(None, "length"), {})] * 2
        res = await self.run_one(max_tokens=2000)
        self.assertEqual(res["status"], "error")
        self.assertIn("finish_reason=length", res["error"])

    async def test_empty_content_without_truncation_is_a_clear_error(self):
        self.script = [(200, ok_body(None, "stop"), {})]
        res = await self.run_one()
        self.assertEqual(res["status"], "error")
        self.assertIn("empty content", res["error"])
        self.assertNotIn("NoneType", res["error"])

    async def test_200_with_error_body_surfaces_provider_message(self):
        self.script = [(200, {"error": {"message": "upstream exploded"}}, {})] * 3
        res = await self.run_one()
        self.assertEqual(res["status"], "error")
        self.assertIn("upstream exploded", res["error"])


class FailureSummaryTests(ScriptedServerCase):
    async def test_execute_all_prints_failure_summary(self):
        self.script = [(401, {"error": "bad key"}, {}),
                       (200, ok_body('{"choice": "CHEAP"}'), {})]
        reqs = [self.request("c1"), self.request("c2")]
        buf = io.StringIO()
        with contextlib.redirect_stdout(buf):
            await self.client._execute_all_async(reqs)
        self.assertIn("1/2 requests failed", buf.getvalue())
        self.assertIn("401", buf.getvalue())


if __name__ == "__main__":
    unittest.main()
