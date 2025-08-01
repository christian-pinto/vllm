# SPDX-License-Identifier: Apache-2.0
# SPDX-FileCopyrightText: Copyright contributors to the vLLM project

import weakref

import pytest

from vllm import LLM, PoolingParams, PoolingRequestOutput
from vllm.distributed import cleanup_dist_env_and_memory

from ...models.utils import check_embeddings_close

MODEL_NAME = "intfloat/multilingual-e5-small"

PROMPTS = [
    "Hello, my name is",
    "The president of the United States is",
    "The capital of France is",
    "The future of AI is",
]

TOKEN_IDS = [
    # Using ID={0, 1, 2, 3} results in NaN values,
    # so we add this offset of 1000
    [1000],
    [1000, 1001],
    [1000, 1002, 1001],
    [1000, 1003, 1001, 1002],
]


@pytest.fixture(autouse=True)
def v1(run_with_both_engines):
    # Simple autouse wrapper to run both engines for each test
    # This can be promoted up to conftest.py to run for every
    # test in a package
    pass


@pytest.fixture(scope="module")
def llm():
    # pytest caches the fixture so we use weakref.proxy to
    # enable garbage collection
    llm = LLM(model=MODEL_NAME,
              max_num_batched_tokens=32768,
              tensor_parallel_size=1,
              gpu_memory_utilization=0.75,
              enforce_eager=True,
              seed=0)

    with llm.deprecate_legacy_api():
        yield weakref.proxy(llm)

        del llm

    cleanup_dist_env_and_memory()


def assert_outputs_match(o1: list[PoolingRequestOutput],
                         o2: list[PoolingRequestOutput]):
    check_embeddings_close(
        embeddings_0_lst=[o.outputs.data for o in o1],
        embeddings_1_lst=[o.outputs.data for o in o2],
        name_0="hf",
        name_1="vllm",
        tol=1e-2,
    )


@pytest.mark.skip_global_cleanup
@pytest.mark.parametrize('prompt_token_ids', TOKEN_IDS)
def test_v1_v2_api_consistency_single_prompt_tokens(llm: LLM,
                                                    prompt_token_ids):
    pooling_params = PoolingParams()

    with pytest.warns(DeprecationWarning, match="'prompt_token_ids'"):
        v1_output = llm.encode(prompt_token_ids=prompt_token_ids,
                               pooling_params=pooling_params)

    v2_output = llm.encode({"prompt_token_ids": prompt_token_ids},
                           pooling_params=pooling_params)
    assert_outputs_match(v1_output, v2_output)


@pytest.mark.skip_global_cleanup
def test_v1_v2_api_consistency_multi_prompt_tokens(llm: LLM):
    pooling_params = PoolingParams()

    with pytest.warns(DeprecationWarning, match="'prompt_token_ids'"):
        v1_output = llm.encode(prompt_token_ids=TOKEN_IDS,
                               pooling_params=pooling_params)

    v2_output = llm.encode(
        [{
            "prompt_token_ids": p
        } for p in TOKEN_IDS],
        pooling_params=pooling_params,
    )
    assert_outputs_match(v1_output, v2_output)


@pytest.mark.skip_global_cleanup
def test_multiple_pooling_params(llm: LLM):
    pooling_params = [
        PoolingParams(),
        PoolingParams(),
        PoolingParams(),
        PoolingParams(),
    ]

    # Multiple PoolingParams should be matched with each prompt
    outputs = llm.encode(PROMPTS, pooling_params=pooling_params)
    assert len(PROMPTS) == len(outputs)

    # Exception raised, if the size of params does not match the size of prompts
    with pytest.raises(ValueError):
        outputs = llm.encode(PROMPTS, pooling_params=pooling_params[:3])

    # Single PoolingParams should be applied to every prompt
    single_pooling_params = PoolingParams()
    outputs = llm.encode(PROMPTS, pooling_params=single_pooling_params)
    assert len(PROMPTS) == len(outputs)

    # pooling_params is None, default params should be applied
    outputs = llm.encode(PROMPTS, pooling_params=None)
    assert len(PROMPTS) == len(outputs)


@pytest.mark.skip_global_cleanup
def test_right_side_truncation(llm: LLM):
    # Embeddings models should truncate the end of the prompt
    tokenizer = llm.get_tokenizer()
    assert tokenizer.truncation_side == "right"
