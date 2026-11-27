# Proposal: fix 4 for agent-roles-and-ownership

## Why
The verifier found problems in `agent-roles-and-ownership` that this change fixes. The findings are listed below with their ids; each task of this change names the ones it answers.

## What Changes
- F-b5f87b40, F-7e9a81fb (blocker): test gate failed (+1 more): `sh .l4/gates/test.sh` failed: exit code 1; failing: tests.unit.admin_api.test_state_after_change_fix3::test_C_1a3fd676_transfer_and_role_answers_show_the_stored_state | new tests failed: tests.unit.admin_api.test_state_after_change_fix3::test_C_1a3fd676_transfer_and_role_answers_show_the_stored_state

      Failing tests as the verifier recorded them:
      tests.unit.admin_api.test_state_after_change_fix3::test_C_1a3fd676_transfer_and_role_answers_show_the_stored_state (assertion, test):
        >       assert to_publisher.status_code == 200, to_publisher.text
        E       AssertionError: Internal Server Error
        E       assert 500 == 200
        E        +  where 500 = <Response [500 Internal Server Error]>.status_code
        ../../tests/unit/admin_api/test_state_after_change_fix3.py:326: AssertionError

## Impact
The code and the tests of `agent-roles-and-ownership`.
