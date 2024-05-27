from testConfig import TestConfig
from trafficFlowTests import TrafficFlowTests
import arguments


def main() -> None:
    args = arguments.parse_args()
    tc = TestConfig(args.config)
    tft = TrafficFlowTests(tc)

    for test in tft._tc.GetConfig():
        tft.run(test, args.evaluator_config)

        if args.evaluator_config:
            if not tft.evaluate_run_success():
                print(f"Failure detected in {test['name']} results")


if __name__ == "__main__":
    main()
