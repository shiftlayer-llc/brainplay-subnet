<div align = "center">

![BrainPlay Logo](./docs/brainplay.jpg)

# Brainplay
</div>


Brainplay is a subnet of Bittensor designed to benchmark AI models through competitive gameplay. Instead of relying solely on abstract mathematical scores, this approach allows people to visually understand a model’s performance by watching it play interesting and engaging games.

## 🎯 Key Idea

Traditional model evaluation methods can be difficult to interpret and lack visibility for general audiences. Brainplay makes AI benchmarking more accessible and entertaining by using games as the evaluation method.
By observing AI models competing in games, users can intuitively grasp which models perform best, making AI evaluation more **transparent**, **understandable**, and **fun**.

## v2.0 Overview

- Uses TVM (Targon) for miner model submission and validator-side querying
- Both miners and validators require a Targon API key
- Miners deploy models via Targon; validators query server endpoints miners deployed via TVM
- No long-lived miner server; validator remains CPU-only
- Miners must have sufficient Targon credits to deploy and serve on TVM

## 🎮 Implemented & Upcoming Games

- ✅ Codenames (first implemented game)
- 🚀 More games coming soon! (We plan to add more interesting games to further diversify benchmarking.)

### How `codenames` works
	1.	Each game consists of two teams.
	2.	Each team is composed of two miners (AI models).
	3.	The teams compete in a game.
	4.	The winning team's miners receive a score.
For comprehensive details about Codenames, please visit: [https://en.wikipedia.org/wiki/Codenames_(board_game)](https://en.wikipedia.org/wiki/Codenames_(board_game))

Official rules PDF (stored in repo): [Codenames Rules](./docs/games/codenames%20-%20rules.pdf)

### Next upcoming competition
- [20 Questions](https://en.wikipedia.org/wiki/20Q)


## Rewards mechanism
The reward mechanism in Brainplay is designed to incentivize AI models (miners) to perform optimally during gameplay. Here's how it works:

1. **Winning Team Rewards**: 
   - The team that wins the game receives a reward. Each miner in the winning team is awarded a score based on their staking amount and performance.

2. **Reward Calculation**:
   - The reward is calculated based on the outcome of the game and the staking amount of each miner. For instance, if the "red" team wins, the miners in the red team receive a higher reward compared to the blue team, with the reward being proportional to their staking amount. Conversely, if the "blue" team wins, the blue team miners receive the reward.

3. **Reward Distribution**:
   - The rewards are distributed as an array of scores. For example, if the red team wins, the reward array might look like `[1.0, 1.0, 0.0, 0.0]`, where the first two values represent the scores for the red team miners, and the last two values represent the scores for the blue team miners. The actual values are adjusted based on the staking amounts.

4. **Transparency and Fairness**:
   - The reward mechanism is designed to be transparent and fair, ensuring that all miners have an equal opportunity to earn rewards based on their performance in the game and their staking contributions.

This reward system not only motivates the miners to perform better but also provides a clear and understandable metric for evaluating the effectiveness of different AI models in competitive scenarios, while also considering their staking commitments.


## Installation

### 1. **Hardware Requirements**

- The validator requires no additional dependencies beyond a standard CPU node.

- Miners are served via TVM on Targon, so you do not need to run a long-lived miner server. Hardware requirements depend on the model you deploy to Targon, not on your local machine.

- Validators query serverless endpoints via TVM and require a configured Targon API key.

### 2. **Software Requirements**

- **Operating System** (Ubuntu 22.04.04+ recommended)
- **Python Version** (Python 3.10 + recommended)

### **Getting code**

```bash
git clone https://github.com/shiftlayer-llc/brainplay-subnet.git
```

### Adding .env file

```bash
cp .env.example .env
```

### Configuring API keys

Add Targon API key (required for both miners and validators) to your `.env` file.
If you're a validator, add your OpenAI API key and wandb key before running your node.

```env
TARGON_API_KEY=your-targon-api-key # required for both miners and validators
OPENAI_KEY=sk-your-key-here        # required for validators only
WANDB_API_KEY=your-wandb-api-key   # required for validators only
```

### Setting up a Virtual Environment

To ensure that your project dependencies are isolated and do not interfere with other projects, it's recommended to use a virtual environment. Follow these steps to set up a virtual environment:

1. **Navigate to your project directory**:
   ```bash
   cd brainplay-subnet
   ```

2. **Create a virtual environment**:
   ```bash
   python3 -m venv venv
   ```

3. **Activate the virtual environment**:
   - On macOS and Linux:
     ```bash
     source venv/bin/activate
     ```
   - On Windows:
     ```bash
     .\venv\Scripts\activate
     ```

4. **Verify the virtual environment is active**:
   You should see `(venv)` at the beginning of your command line prompt, indicating that the virtual environment is active.

5. **Deactivate the virtual environment**:
   When you're done working in the virtual environment, you can deactivate it by simply running:
   ```bash
   deactivate
   ```

By using a virtual environment, you ensure that your project's dependencies are managed separately from other projects, reducing the risk of version conflicts.


### Installing Dependencies

Ensure you have the required dependencies installed. You can use the following command to install them:

```bash
pip install -e .
```

### Running Validator

#### Option 1: Manual Update (Traditional Method)

Run the validator manually and handle updates yourself:

```bash
python neurons/validator.py --wallet.name test_validator --wallet.hotkey h1 --netuid 117 --logging.info
```
or if you're using PM2

```bash
pm2 start neurons/validator.py --name brainplay-manual-validator -- --wallet.name test_validator --wallet.hotkey h1 --netuid 117 --logging.info
```



**Note**: With this method, you need to manually pull updates and restart the validator when new versions are available.

#### Option 2: Auto-Update (Recommended)

Set up automatic updates that keep your validator current with the latest code:

1. **First-time setup** (run once after cloning):
   ```bash
   # Set up git hooks and script permissions
   chmod +x scripts/*.sh && chmod +x .git/hooks/post-merge 2>/dev/null || ./scripts/setup_hooks.sh
   ```
   
   **Note**: This setup configures git to ignore file permission changes, preventing conflicts during future pulls.

2. **Run the auto-validator**:
   ```bash
   ./scripts/run_auto_validator.sh --wallet.name brainplay_validator --wallet.hotkey default --netuid 117 --logging.info
   ```

**Benefits of Auto-Update**:
- ✅ Automatically checks for updates every 5 minutes
- ✅ Pulls latest code and restarts validator when updates are available
- ✅ Maintains validator uptime and ensures you're always running the latest version
- ✅ Handles script permissions automatically after git pulls
- ✅ Creates backups before updates
- ✅ Comprehensive logging of all operations

### Running Miner (TVM / Targon)

v2.0 miners do not run a long-lived `neurons/miner.py` process. The miner flow is:

1. Deploy a serverless model endpoint on Targon.
2. Wait for the endpoint to become ready.
3. Commit that endpoint UID on-chain so validators can discover and query it.

The deployment/commit entrypoint is [`deploy/miner.py`](./deploy/miner.py).

#### Miner prerequisites

- A funded Targon account with enough credits to deploy and serve your model
- A Bittensor wallet + hotkey registered on the subnet
- `TARGON_API_KEY` available in `.env` or already stored via the Targon CLI
- The repo installed with:

```bash
pip install -e .
```

#### Basic miner command

```bash
python deploy/miner.py \
  --competition twentyq \
  --model "your-org/your-model" \
  --wallet owner \
  --hotkey default \
  --network test \
  --netuid 335
```

What this command does:

- Reads the selected profile from `deploy/profiles/{competition}.json`
- Injects runtime env vars such as `MODEL`, `MINER_HOTKEY`, and `REASONING`
- Deploys one serverless container on Targon
- Waits until the `/meta` endpoint reports the server is ready
- Commits the endpoint UID to chain under the selected competition key(s)

#### Common miner commands

Deploy only for Codenames:

```bash
python deploy/miner.py \
  --competition codenames \
  --model "your-org/your-model" \
  --wallet owner \
  --hotkey default
```

Deploy only for 20 Questions:

```bash
python deploy/miner.py \
  --competition twentyq \
  --model "your-org/your-model" \
  --wallet owner \
  --hotkey default
```

Deploy one endpoint and commit it for both currently supported competitions:

```bash
python deploy/miner.py \
  --competition all \
  --model "your-org/your-model" \
  --wallet owner \
  --hotkey default
```

Pass extra SGLang flags if your model needs them:

```bash
python deploy/miner.py \
  --competition twentyq \
  --model "Qwen/Qwen2.5-32B-Instruct" \
  --sglang-extra-args "--context-length 32768 --enable-torch-compile" \
  --reasoning low \
  --wallet owner \
  --hotkey default
```

#### Miner CLI arguments

- `--competition`: profile name under `deploy/profiles/`
- `--model`: model name/path passed into the deployment container
- `--sglang-extra-args`: extra SGLang server flags
- `--reasoning`: reasoning effort metadata exposed to validators; one of `none`, `minimal`, `low`, `medium`, `high`, `xhigh`
- `--wallet`: Bittensor wallet name
- `--hotkey`: Bittensor hotkey name
- `--wallet-path`: optional custom wallet directory
- `--network`: subtensor network, for example `finney` or `test`
- `--netuid`: subnet netuid
- `--commit-period`: optional chain commitment period override

#### Profile JSON files

Miner profiles live in [`deploy/profiles/`](./deploy/profiles). Each JSON file defines the Targon serverless container spec used by `deploy/miner.py`.

Current profiles include:

- `deploy/profiles/codenames.json`
- `deploy/profiles/twentyq.json`
- `deploy/profiles/all.json`

At the moment these files intentionally use the same container template. They still exist separately so each competition can evolve independently later without changing the deployment workflow.

Each profile contains:

- `version`: config schema version for Targon
- `app_name`: logical app name
- `containers`: list of containers to deploy
- `containers[].name`: container name; `${NAME}` is filled in by `deploy/miner.py`
- `containers[].resource`: Targon resource tier, for example `h100-small`
- `containers[].image`: container image to run
- `containers[].port`: exposed service port
- `containers[].env`: runtime environment variables injected into the container
- `containers[].replicas`: min/max replica settings and concurrency target

Important env placeholders used in these JSON files:

- `${NAME}`: generated container name such as `brainplay-twentyq`
- `${MODEL}`: value passed via `--model`
- `${SGLANG_EXTRA_ARGS}`: value passed via `--sglang-extra-args`
- `${MINER_HOTKEY}`: hotkey SS58 address from the wallet
- `${REASONING}`: value passed via `--reasoning`

#### Difference between `codenames.json`, `twentyq.json`, and `all.json`

- `codenames.json`: deploys one endpoint and commits it only under the `codenames` key on-chain
- `twentyq.json`: deploys one endpoint and commits it only under the `twentyq` key on-chain
- `all.json`: deploys one endpoint and commits the same endpoint under both `codenames` and `twentyq`

That means `all.json` is for miners who want one shared model endpoint to serve multiple competitions. If you want different models or different runtime settings per competition, deploy them separately with `codenames.json` and `twentyq.json`.

#### On-chain commitment shape

The miner keeps the original plain JSON commitment format. After deployment, the committed payload looks like this:

```json
{
  "codenames": "serv-u-xxxxxxxxxxxxxxxx",
  "twentyq": "serv-u-yyyyyyyyyyyyyyyy"
}
```

If you deploy with `--competition all`, both keys point to the same endpoint UID:

```json
{
  "codenames": "serv-u-xxxxxxxxxxxxxxxx",
  "twentyq": "serv-u-xxxxxxxxxxxxxxxx"
}
```

Validators read this commitment from chain and pick the endpoint that matches the competition they are running.
