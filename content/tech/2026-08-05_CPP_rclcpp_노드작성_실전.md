---
publish: true
title: "C++ rclcpp — 노드 작성 실전"
date: 2026-08-05T11:15:00+09:00
tags:
  - C++
  - rclcpp
  - ROS2
  - 콜백
  - executor
description: "파이썬으로 잡은 노드 개념을 C++로 옮기면 문법보다 수명과 스레딩이 문제가 돼요. 멤버로 잡아야 산다는 것과 콜백 안에서 기다리지 않는다는 것, 둘이 사고의 대부분을 막아요."
section: tech
---

주기 제약이나 하드웨어 접점이 있는 층은 대체로 C++입니다. 제어 프레임워크의 컨트롤러, 내비게이션 플러그인, 모션 플래닝 코어, 하드웨어 인터페이스가 그래요. 파이썬으로 노드 개념을 잡았어도 이 층을 읽으려면 C++ 쪽 철자를 알아야 하는데, 정작 어려운 건 문법이 아니라 C++이라서 새로 생기는 문제예요.

## 그림은 같고 철자만 달라요

노드는 `rclcpp::Node`를 상속한 클래스이고, 생성자에서 통신 객체를 만들어 멤버로 잡아요.

```cpp
class ArmMonitor : public rclcpp::Node {
public:
    ArmMonitor() : Node("arm_monitor") {
        sub_ = create_subscription<sensor_msgs::msg::JointState>(
            "/joint_states", 10,
            [this](sensor_msgs::msg::JointState::SharedPtr msg) {   // 콜백 = 람다 + this 캡처
                last_ = std::move(msg);
            });
        timer_ = create_wall_timer(std::chrono::milliseconds(100),
                                   [this] { report(); });
    }
private:
    void report() {
        if (last_) RCLCPP_INFO(get_logger(), "joints: %zu", last_->name.size());
    }
    rclcpp::Subscription<sensor_msgs::msg::JointState>::SharedPtr sub_;
    rclcpp::TimerBase::SharedPtr timer_;
    sensor_msgs::msg::JointState::SharedPtr last_;
};
```

읽는 데 필요한 대응은 이 정도예요. 타입이 템플릿 인자로 들어가고, QoS 자리의 `10`은 최근 열 개만 버퍼에 유지한다는 뜻이고, 콜백은 람다예요.

**만들어진 객체를 멤버로 잡는 건 문법이 아니라 생존 조건이에요.** 반환값을 버리면 참조 카운트가 0이 되어 구독이 그 자리에서 해제돼요. 에러도 안 나고 그냥 콜백이 한 번도 안 불려요. "구독을 만들었는데 메시지가 안 온다"의 1순위 원인이라, 디스커버리를 의심하기 전에 멤버 보관부터 확인하는 게 순서예요.

## SharedPtr이 세 번 나오는 이유

노드와 구독과 타이머와 메시지가 전부 공유 포인터로 오가요. 실행기와 사용자 코드가 노드를 함께 잡고, 미들웨어와 콜백이 메시지를 함께 잡으니, 마지막에 놓는 쪽이 지우는 구조로 설계된 거예요. [[2026-08-05_CPP_소유권과_수명_스마트포인터|소유권과 수명]]에서 본 공유 소유가 그대로 쓰인 자리예요.

콜백의 `this` 캡처가 안전한 이유도 같은 글에서 설명돼요. 타이머와 구독이 노드의 멤버라서, 콜백이 실행될 수 있는 동안 노드는 반드시 살아 있어요. 반대로 노드 밖으로 콜백을 넘기는 순간 그 보장이 사라지니 `shared_from_this()` 값 캡처로 바꿔야 해요.

메시지를 공유 포인터로 받는 덕에 큰 스캔이나 이미지를 구독자 여럿이 복사 없이 나눠 보는 것도 같은 원리예요.

## 콜백 안에서 기다리지 않아요

`rclcpp::spin(node)`은 실행기를 만들어 콜백들을 돌려주는 반복문이에요. 기본은 한 번에 하나씩, 순서대로 실행돼요. 이 기본값이 주는 보장이 커요. 콜백끼리 동시에 안 도니까 콜백들만 만지는 멤버 변수엔 잠금이 필요 없어요.

대신 대가가 있어요. 콜백 하나가 오래 걸리면 나머지 전부가 밀려요. 구독 콜백에서 1초짜리 계산을 하면 그동안 타이머도 서비스도 안 돌아요.

여기서 가장 자주 밟는 함정이 나와요. **콜백 안에서 같은 노드의 다른 응답을 동기로 기다리면 영원히 안 와요.** 그 응답을 처리할 스레드가 자기 자신이거든요. 교착 증상 1순위예요.

콜백이 정말 오래 걸려야 한다면 두 갈래예요. 계산을 다른 스레드로 떼거나, 멀티스레드 실행기와 콜백 그룹으로 병렬을 허용해요.

```cpp
rclcpp::executors::MultiThreadedExecutor exec;   // 스레드 여럿이 콜백을 나눠 돎
exec.add_node(node);
exec.spin();
```

멀티스레드로 바꾸는 순간 "콜백끼리 안 겹친다" 보장이 사라져요. 그걸 다시 통제하는 도구가 콜백 그룹이에요. 같은 상호배타 그룹에 속한 콜백끼리는 여전히 하나씩 돌고, 재진입 그룹은 같은 콜백조차 동시 실행을 허용해요.

설계 감각은 이래요. 센서 콜백과 제어 타이머는 다른 그룹으로 분리해 병렬을 허용하고, 상태를 공유하는 콜백들은 같은 그룹에 묶어 잠금 없이 안전하게 둬요. 그룹 분리 없이 멀티스레드 실행기만 켜면 [[2026-08-05_CPP_동시성_센서수신과_제어루프|동시성]]에서 본 데이터 레이스가 그대로 돌아와요.

## 파라미터는 선언이 먼저예요

선언하지 않은 파라미터를 읽으면 예외가 나요. 파이썬도 같지만 C++에서는 노드 시작 직후 크래시로 만나게 돼요.

```cpp
declare_parameter("serial_port", "/dev/ttyUSB0");
declare_parameter("cal_zero", std::vector<double>{});

auto port = get_parameter("serial_port").as_string();
```

런타임 변경을 받으려면 파라미터 콜백을 등록해요. 검증 람다를 걸고 반환값으로 승인과 거부를 알리는 형태예요. 캘리브레이션 값을 재빌드 없이 조정하는 자리가 정확히 이 패턴이에요.

## 액션은 콜백 세 개로 쪼개져요

관절 궤적을 보내고 실행을 지켜보는 통신은 비동기 콜백 체인이라, 구조를 알고 봐야 읽혀요.

```cpp
rclcpp_action::Client<FJT>::SendGoalOptions opts;
opts.goal_response_callback = [](auto handle) {
    // 1단계: 서버가 목표를 받았나 (핸들이 널이면 거부)
};
opts.feedback_callback = [](auto, auto fb) {
    // 2단계: 실행 중 피드백 — 여러 번 불림
};
opts.result_callback = [](const auto& result) {
    // 3단계: 최종 결과
};
client_->async_send_goal(goal, opts);
```

세 단계가 갈린 이유는 액션의 수명이 길어서예요. 목표 수락은 즉시, 실행 완료는 수 초 뒤이고 그 사이 피드백이 흘러요. 전부 콜백이니 앞 절의 규칙이 그대로 적용돼요. 결과를 콜백 안에서 동기로 기다리면 안 되고, 상태를 멤버에 적어 두고 반환해요.

## 빌드에서 자주 막히는 두 곳

C++ 노드는 컴파일러 한 줄로는 못 짓고 빌드 도구를 거쳐요. 설정 파일의 뼈대는 의존 선언과 실행 파일 등록과 설치 규칙이에요.

```cmake
find_package(rclcpp REQUIRED)
add_executable(arm_monitor src/arm_monitor.cpp)
ament_target_dependencies(arm_monitor rclcpp sensor_msgs)
install(TARGETS arm_monitor DESTINATION lib/${PROJECT_NAME})
```

여기서 막히는 건 둘이에요. 설치 규칙을 빼먹으면 빌드는 되는데 실행 명령이 파일을 못 찾고, 빌드 후 환경 설정을 다시 읽지 않으면 방금 지은 게 안 보여요. 둘 다 에러 메시지가 원인을 직접 가리키지 않아서 한 번씩은 겪게 돼요.

## 두 규칙이면 대부분 막혀요

rclcpp는 새 개념이 아니라 아는 개념 위에 C++의 수명·스레딩 규칙이 얹힌 층이에요. 멤버로 잡아야 산다는 것과 콜백 안에서 기다리지 않는다는 것, 이 둘만 지켜도 C++ 노드의 사고 대부분이 막히고 나머지는 철자 바꾸기예요.

콜백에서 예외가 새어 나갈 때 무슨 일이 생기는지는 [[2026-08-05_CPP_에러처리_로봇노드_실패정책|에러 처리]]에 있어요.
