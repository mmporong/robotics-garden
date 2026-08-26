---
title: "Unitree Go2 push curriculum의 불확실한 회복률 이득"
date: 2026-08-26T10:13:50+09:00
tags:
  - Isaac Lab
  - Unitree Go2
  - PPO
  - domain randomization
  - disturbance recovery
description: "4,096개 병렬 환경에서 학습한 Unitree Go2 baseline과 push curriculum을 7,020개 trial로 비교하고, 작은 회복률 차이와 에너지 비용을 함께 검증한 기록"
publish: true
section: physical-ai
---

Unitree Go2가 거친 지형에서 속도 명령을 따라 걷고, 몸통에 외란을 받은 뒤에도 자세와 속도를 회복하도록 학습했어요. NVIDIA Isaac Sim과 Isaac Lab에서 4,096개 환경을 병렬로 실행했고, RSL-RL PPO로 baseline과 push curriculum을 각각 3개 seed에서 학습했어요.

비교 조건은 지형, 관측, 보상, 네트워크, 학습 budget을 같게 두고 `events.push_robot`만 바꿨어요. push curriculum의 회복률은 baseline보다 `0.0617%p` 높았지만 seed별 방향이 엇갈렸고, bootstrap 신뢰구간도 0을 포함했어요. 속도 추적 오차가 줄어든 대신 torque와 mechanical power proxy가 늘어난 부분까지 같은 표에 남겼어요.

<figure class="fig"><img src="../assets/g006_policy_comparison.gif" alt="Unitree Go2 baseline과 push curriculum 정책의 거친 지형 주행 비교"><figcaption>왼쪽은 baseline, 오른쪽은 push curriculum 정책이에요. 학습과 평가가 끝난 checkpoint를 환경 하나에서 재생해 촬영했어요.</figcaption></figure>

## 학습 스택과 실행 조건

| 구분 | 도구와 버전 | 역할 |
| --- | --- | --- |
| 물리·로봇 시뮬레이션 | NVIDIA Isaac Sim `4.5.0` | Go2 articulation, 접촉, PhysX 물리 계산 |
| RL 환경 | Isaac Lab `2.1.1`, commit `90b79bb2d44feb8d833f260f2bf37da3487180ba` | 관측·보상·event·curriculum 구성 |
| 강화학습 | RSL-RL `2.3.3` | PPO rollout, GAE, actor-critic update, checkpoint 저장 |
| 텐서 연산 | PyTorch `2.7.0+cu128`, CUDA `12.8` | 정책 추론과 학습 |
| 실험 제어 | PowerShell `7.6.5`, Python `3.10.15` | scale ladder, 6개 run queue, 재개·검증·보고서 생성 |
| 로그 | TensorBoard `2.21.0` | reward, episode length, terrain·push curriculum 상태 기록 |
| 자원 감시 | `nvidia-smi` | 2초 간격 VRAM 측정과 종료 후 GPU 회수 확인 |
| 시각 증거 | Gymnasium RecordVideo, FFmpeg `8.1` | checkpoint 재생, GIF와 비교 스크린샷 생성 |

실행 장비는 Windows 11 Pro와 NVIDIA GeForce RTX 3060 12GB였어요. production run에서 측정한 최대 peak VRAM은 `9,022 MiB`였어요.

### headless 학습이 뜻하는 것

6개 production 학습 보고서에는 모두 `headless=true`가 기록돼 있어요. 학습 중에는 Isaac Sim 창과 viewport를 띄우지 않았고 RGB 카메라 프레임도 만들지 않았어요. 물리 시뮬레이션과 정책 학습은 GPU에서 계속 실행했어요.

정책 입력은 화면이 아니라 `235`차원 상태 벡터예요. 몸통 속도와 자세, 관절 상태, 직전 action, 목표 속도, 지면 높이 ray scan이 들어가요. 지면 정보도 RGB나 depth image가 아니라 로봇 주변 높이를 읽은 `187`개 ray sample이에요. 이 구성으로 12GB GPU에서 4,096개 환경을 병렬로 실행했어요.

영상은 학습과 분리해 만들었어요. 학습이 끝난 뒤 checkpoint 하나와 환경 하나만 불러와 headless viewport capture를 켰어요. 이때의 `headless`는 UI를 숨긴다는 뜻이고, 영상 프레임을 만드는 viewport와 D3D12 renderer는 별도로 활성화했어요. GIF 렌더링 비용은 production 학습 처리량에 포함되지 않아요.

## 환경과 Markov decision process

### 시뮬레이션과 제어 주기

| 설정 | 값 |
| --- | ---: |
| PhysX simulation timestep | `0.005 s` (`200 Hz`) |
| control decimation | `4` physics steps |
| policy/control timestep | `0.02 s` (`50 Hz`) |
| episode 제한 | `20 s`, 최대 1,000 policy steps |
| velocity command 갱신 | `10 s` |
| command 범위 | x/y 선속도 `-1.0~1.0 m/s`, yaw rate `-1.0~1.0 rad/s` |

PPO가 action 하나를 내면 같은 관절 목표를 네 번의 PhysX step 동안 적용해요. 몸통이 바닥에 닿으면 episode를 종료하고, 20초를 채우면 timeout으로 reset해요.

### 관측과 action

| policy observation | 차원 | 학습 시 처리 |
| --- | ---: | --- |
| body linear velocity | 3 | uniform noise `±0.1` |
| body angular velocity | 3 | uniform noise `±0.2` |
| projected gravity | 3 | uniform noise `±0.05` |
| velocity command | 3 | x/y/yaw 목표 |
| relative joint position | 12 | uniform noise `±0.01` |
| relative joint velocity | 12 | uniform noise `±1.5` |
| previous action | 12 | 직전 정책 출력 |
| height scan | 187 | uniform noise `±0.1`, `[-1, 1]` clip |
| 합계 | 235 | 하나의 policy vector로 연결 |

action은 12개 관절의 position target이에요. 정책 출력에 Go2 기본 관절 자세를 offset으로 더하고 scale `0.25`를 적용해요. 토크를 직접 출력하는 정책은 아니에요.

### actor와 critic

actor와 critic은 관측 `235`차원을 각각 입력받는 MLP예요. hidden layer는 `[512, 256, 128]`, activation은 ELU를 사용했어요. actor는 12차원 action mean을 출력하고 초기 exploration noise standard deviation은 `1.0`이에요. critic은 state value 하나를 출력해요. empirical observation normalization은 사용하지 않았어요.

```text
Actor: 235 -> 512 -> 256 -> 128 -> 12
Critic: 235 -> 512 -> 256 -> 128 -> 1
Activation: ELU
```

## 보상 함수와 동역학적 의도

runtime log에서 확인한 non-zero reward weight는 다음과 같아요.

| reward term | weight | 의도 |
| --- | ---: | --- |
| `track_lin_vel_xy_exp` | `+1.5` | x/y 속도 명령 추종 |
| `track_ang_vel_z_exp` | `+0.75` | yaw rate 명령 추종 |
| `lin_vel_z_l2` | `-2.0` | 몸통의 수직 흔들림 억제 |
| `ang_vel_xy_l2` | `-0.05` | roll/pitch 방향 각속도 억제 |
| `dof_torques_l2` | `-0.0002` | 큰 관절 torque 억제 |
| `dof_acc_l2` | `-2.5e-7` | 급격한 관절 가속 억제 |
| `action_rate_l2` | `-0.01` | action 변화량 억제 |
| `feet_air_time` | `+0.01` | 발의 swing time 유도 |

`flat_orientation_l2`와 `dof_pos_limits`는 manager에 등록돼 있지만 weight가 `0.0`이라 목적함수에는 기여하지 않아요. Go2 몸통의 base contact는 reward가 아니라 termination 조건으로 처리했어요.

속도 추종 보상만 키우면 원하는 속도를 빨리 맞출 수 있지만 큰 토크나 급한 관절 운동을 허용하기 쉬워요. 반대로 torque, joint acceleration, action rate penalty를 너무 크게 잡으면 자세는 매끈해져도 외란 뒤에 필요한 충격량을 만들지 못할 수 있어요. 이번 비교에서는 보상을 고정했기 때문에 push event가 정책의 외란 경험만 바꿨어요.

## 거친 지형과 공통 randomization

학습 지형은 Isaac Lab rough terrain generator로 만들었어요. `8 m × 8 m` patch를 10행 20열로 놓고 계단, 역계단, box, random rough, 경사, 역경사를 섞었어요. Go2 크기에 맞춰 box 높이는 `0.025~0.10 m`, random rough noise는 `0.01~0.06 m`로 낮췄어요.

terrain curriculum은 로봇이 해당 patch에서 이동한 거리를 보고 난도를 올리거나 내려요. baseline과 push curriculum 모두 같은 지형 curriculum을 썼어요. 두 정책의 차이를 외란 event 하나로 제한하기 위한 조건이에요.

학습 중에는 다음 변동을 공통으로 적용했어요.

- base mass에 `-1~+3 kg`를 더했어요.
- reset 위치는 x/y 각각 `-0.5~0.5 m`, yaw는 `-3.14~3.14 rad`에서 뽑았어요.
- 관측값에는 관측 표에 적은 uniform noise를 넣었어요.
- startup material 값은 static friction `0.8`, dynamic friction `0.6`, restitution `0.0`으로 고정했어요.
- Go2 설정에서는 base center-of-mass randomization을 쓰지 않았어요.

평가에서는 observation noise와 event randomization을 모두 껐어요. 학습 때의 랜덤 요인이 평가 분산에 섞이지 않도록 terrain, command, 초기 상태, push 조건을 고정했어요.

## PPO의 배치와 epoch 계산

| 항목 | 값 |
| --- | ---: |
| algorithm | PPO |
| rollout length | 환경당 24 steps |
| parallel environments | 4,096 |
| rollout batch | 98,304 transitions/iteration |
| mini-batches | epoch당 4개 |
| mini-batch 크기 | 24,576 transitions |
| learning epochs | rollout batch당 5 epochs |
| iterations | run당 1,500 |
| optimizer updates | iteration당 20회, run당 30,000회 |
| learning rate | `1.0e-3`, adaptive schedule |
| PPO clip | `0.2` |
| discount `gamma` | `0.99` |
| GAE `lambda` | `0.95` |
| target KL | `0.01` |
| entropy coefficient | `0.01` |
| value loss coefficient | `1.0` |
| clipped value loss | 사용 |
| gradient norm limit | `1.0` |
| checkpoint interval | 50 iterations |

iteration 하나에서 4,096개 환경이 각각 24 step을 진행하므로 `98,304`개 transition이 생겨요. 이 rollout batch를 4개로 나누면 mini-batch 하나는 `24,576`개예요. 4개 mini-batch를 5 epoch 반복하므로 iteration마다 optimizer update는 20회예요.

```text
4,096 env × 24 steps = 98,304 transition 수집
98,304 / 4 mini-batches = mini-batch당 24,576 transition
4 mini-batches × 5 epochs = iteration당 20 optimizer updates
1,500 iterations = run당 147,456,000 transition, 30,000 updates
6 production runs = 884,736,000 transition, 180,000 updates
```

여기서 epoch는 새 simulation data를 다시 모으는 횟수가 아니에요. rollout batch를 한 번 무작위로 나눈 4개 mini-batch를 5번 반복해 학습해요. 5 epoch가 끝나면 기존 batch를 버리고 다음 24 step을 수집해요.

## push curriculum

baseline은 학습 중 push event를 껐어요. push curriculum은 10~15초마다 각 환경의 로봇에 body XY 방향 delta velocity를 더해요. 방향은 `0~2π`에서 균일하게 뽑고, 로봇의 현재 yaw를 적용해 world frame으로 변환해요. `is_global_time=false`라서 4,096개 환경의 push timer가 서로 독립적으로 움직여요.

| 학습 구간 | common step | PPO iteration | push magnitude |
| --- | ---: | ---: | ---: |
| stage 0 | `0~11,999` | `0~499` | `0.10~0.25 m/s` |
| stage 1 | `12,000~23,999` | `500~999` | `0.25~0.50 m/s` |
| stage 2 | `24,000~35,999` | `1,000~1,499` | `0.50~1.00 m/s` |

각 iteration이 24 control step이라 stage 경계는 500 iteration 간격과 맞아요. TensorBoard에는 stage별 event 수와 실제 magnitude의 최소·평균·최댓값을 기록해 curriculum이 설정대로 실행됐는지 검사했어요.

push를 body frame에서 뽑은 이유는 로봇의 진행 방향과 외란 방향을 분리해 해석하기 위해서예요. world frame 축으로만 밀면 로봇의 yaw에 따라 앞·뒤·좌·우 의미가 달라져요. body frame 방향을 world frame으로 회전하면 로봇이 어느 방향을 보고 있어도 전방 push는 몸체 전방으로 작용해요.

## 6개 production run

4,096개 환경을 바로 production에 넣지 않았어요. 1,024, 2,048, 4,096 환경 순으로 scale ladder를 실행하고, VRAM과 프로세스 종료 후 GPU 회수 조건을 통과한 뒤 4,096를 공통 환경 수로 정했어요.

| variant | seed | wall time | 평균 steps/s | median steps/s | peak VRAM |
| --- | ---: | ---: | ---: | ---: | ---: |
| baseline | 42 | 4.854 h | 8,548.25 | 8,725.0 | 7,889 MiB |
| baseline | 43 | 4.984 h | 8,333.55 | 8,543.0 | 7,719 MiB |
| baseline | 44 | 4.424 h | 9,478.04 | 9,959.0 | 7,856 MiB |
| push curriculum | 42 | 5.182 h | 8,074.10 | 8,040.5 | 7,780 MiB |
| push curriculum | 43 | 5.190 h | 8,046.65 | 8,178.0 | 7,735 MiB |
| push curriculum | 44 | 4.618 h | 9,036.51 | 9,093.5 | 9,022 MiB |

6개 run은 모두 `1499/1500` iteration 표기까지 완료하고 `model_1499.pt`를 저장했어요. iteration index가 0부터 시작하기 때문에 마지막 표기가 1499예요. run 평균 처리량의 평균은 `8,586.18 steps/s`, 전체 wall time은 `29.25시간`이에요.

## 외란 회복 평가

학습 reward나 영상만으로 정책을 비교하지 않았어요. 각 checkpoint를 별도 headless evaluator에 넣고, 학습 때 쓰지 않은 고정 조건에서 같은 trial grid를 실행했어요.

| 평가 축 | 설정 |
| --- | --- |
| training seeds | 42, 43, 44 |
| evaluation/terrain seed | `20260824` |
| terrain 난도 | held-out row 1, 4, 8 |
| command | 전진 `(0.75, 0, 0)`, 횡이동 `(0, 0.50, 0)`, 회전 `(0.50, 0, 0.50)` |
| push 방향 | body frame 전·후·좌·우 |
| push 크기 | `0.5`, `1.0`, `1.5 m/s` |
| push 시점 | completed step 200, simulation time 4.0초 |
| 회복 판정 구간 | step 201~450 |
| 전체 horizon | 600 steps, 12초 |
| push trials | seed·variant당 108 cells × 10 = 1,080 |
| guardrail trials | seed·variant당 9 cells × 10 = 90 |

회복 성공 조건은 선속도 오차 `0.30 m/s` 이하, yaw rate 오차 `0.30 rad/s` 이하, roll과 pitch 절댓값 `0.35 rad` 이하를 25 step 연속 유지하는 것이에요. 이 조건을 만족해도 몸통이 바닥에 닿거나 12초 horizon까지 생존하지 못하면 성공으로 세지 않았어요.

전체 비교에는 6,480개 push trial과 540개 no-push guardrail trial이 들어갔어요. recovery rate에는 Wilson 95% interval을 계산했고, 108개 고정 stratum을 같은 비중으로 뽑는 paired hierarchical bootstrap을 10,000회 수행했어요.

## 회복률보다 trade-off가 먼저 보였다

| 지표 | baseline | push curriculum | 차이 |
| --- | ---: | ---: | ---: |
| push 회복률 | 3225/3240 (`99.5370%`) | 3227/3240 (`99.5988%`) | `+0.0617%p` |
| push horizon 생존률 | 3235/3240 (`99.8457%`) | 3231/3240 (`99.7222%`) | `-0.1235%p` |
| guardrail 생존률 | 270/270 (`100%`) | 270/270 (`100%`) | `0%p` |
| tracking error squared mean | `0.029994` | `0.027256` | `-9.1290%` |
| yaw error squared mean | `0.014111` | `0.012737` | `-9.7386%` |
| torque L2 mean | `200.289065` | `209.184042` | `+4.4411%` |
| mechanical power proxy | `35.583149` | `36.868460` | `+3.6121%` |

paired bootstrap으로 계산한 회복률 차이 추정치는 `+0.0619%p`, 95% 신뢰구간은 `-0.7716%p~+0.9568%p`였어요. seed 42에서는 push curriculum이 앞섰지만 seed 44에서는 baseline이 앞섰어요. 이 결과로 push curriculum의 우월성을 주장할 수는 없어요.

두 정책의 차이는 비용 지표에서 더 뚜렷했어요. push curriculum 정책은 속도와 yaw 추적 오차가 낮았고 action 변화량도 조금 줄었어요. torque와 mechanical power proxy는 늘었어요. mechanical power는 `sum(abs(torque × joint_velocity))`로 계산한 simulation proxy라서 배터리 소비 전력과 같지 않아요.

외란을 경험한 정책이 더 큰 제어 입력을 쓰면서 명령 추종을 유지하는 쪽으로 학습됐다는 해석은 가능해요. 다만 torque 증가가 실제 접촉 충격, 보행 위상 변경, 높은 관절 속도 중 어디에서 왔는지는 이번 aggregate 지표만으로 분리할 수 없어요. 그 판단에는 발별 ground reaction force와 관절별 torque·velocity time series를 외란 전후 구간으로 나눈 분석이 더 필요해요.

## 재현과 증거 연결

실험 coordinator는 다음 명령으로 시작해요.

```powershell
cd "$HOME\isaac-walk-rl"
.\scripts\run_g006_experiment.ps1
```

coordinator가 training process를 시작할 때 사용한 형식은 다음과 같아요. task와 seed를 바꿔 6개 production run을 만들었어요.

```powershell
cd "$HOME\IsaacLab"
& "$HOME\IsaacLab\_isaac_sim\python.bat" `
  "$HOME\isaac-walk-rl\scripts\bootstrap_train_g006.py" `
  --task Isaac-G006-Velocity-Rough-Go2-PushCurriculum-v0 `
  --num_envs 4096 `
  --max_iterations 1500 `
  --seed 42 `
  --run_name g006_production_push_curriculum_e4096_i1500_s42 `
  --headless
```

한 run의 완료 조건도 exit code 하나로 두지 않았어요. 요청 iteration 도달, TensorBoard와 checkpoint 존재, fatal pattern 부재, GPU 측정 완료, 프로세스 종료 후 GPU 회수를 함께 검사했어요. seed 44 push run에서 새 Codex 앱 GPU context 때문에 회수 게이트가 false-negative를 냈을 때는 checkpoint와 raw log를 다시 검사하고 별도 attestation으로 복구 판정을 남겼어요.

코드와 정량 근거는 실행 당시 commit에 고정했어요.

- [포트폴리오 상세 문서](https://github.com/mmporong/isaac-walk-rl/blob/61bba4bed386aacc21a7742382fa9c36cb6a0fd8/docs/G006_PORTFOLIO.md)
- [실험 계약](https://github.com/mmporong/isaac-walk-rl/blob/61bba4bed386aacc21a7742382fa9c36cb6a0fd8/configs/g006_rough_push.json)
- [정량 결과 원문](https://github.com/mmporong/isaac-walk-rl/blob/61bba4bed386aacc21a7742382fa9c36cb6a0fd8/reports/runs/g006_summary.json)
- [run별 상태와 checkpoint 해시](https://github.com/mmporong/isaac-walk-rl/blob/61bba4bed386aacc21a7742382fa9c36cb6a0fd8/reports/runs/g006_queue_state.json)
- [외란 회복 결과 해석](https://github.com/mmporong/isaac-walk-rl/blob/61bba4bed386aacc21a7742382fa9c36cb6a0fd8/docs/G006_ROUGH_PUSH_RECOVERY.md)
- [GIF·스크린샷·원본 영상 해시](https://github.com/mmporong/isaac-walk-rl/blob/61bba4bed386aacc21a7742382fa9c36cb6a0fd8/docs/G006_VISUAL_EVIDENCE.md)

이 결과는 simulation에서 상태 관측을 사용하는 정책에 한정돼요. 카메라 기반 perception, 실제 Go2 하드웨어, actuator 지연, 통신 지연, 배터리와 열 특성은 다루지 않았어요. variant당 training seed도 3개라 작은 차이를 가르는 통계 검정에는 한계가 있어요. 이번 산출물은 sim-to-real 완료가 아니라, 비교 조건을 통제한 rough-terrain PPO 학습과 외란 회복 평가 파이프라인이에요.
