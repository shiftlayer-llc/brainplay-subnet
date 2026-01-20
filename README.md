<div align = "center">

![BrainPlay Logo](./docs/brainplay.jpg)

# Brainplay
</div>


Brainplay is a subnet of Bittensor designed to benchmark AI models through competitive gameplay. Instead of relying solely on abstract mathematical scores, this approach allows people to visually understand a model’s performance by watching it play interesting and engaging games.

## 🎯 Key Idea

Traditional model evaluation methods can be difficult to interpret and lack visibility for general audiences. Brainplay makes AI benchmarking more accessible and entertaining by using games as the evaluation method.
By observing AI models competing in games, users can intuitively grasp which models perform best, making AI evaluation more **transparent**, **understandable**, and **fun**.

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

### Configuring OpenAI and wandb keys

Add your OpenAI API key (validator only) and wandb key (validator only) to the `.env` file before running validators:

```env
OPENAI_KEY=sk-your-key-here        # required for validators only
WANDB_API_KEY=your-wandb-api-key   # required for validators only
```

Miners deploying via TVM should set `TARGON_API_KEY` in their shell (or log in with `targon auth`) before running the deploy script below.

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

This subnet uses TVM. Miners do not run `neurons/miner.py` on a server. Instead, deploy your model on Targon and commit the endpoint on-chain so validators can query it.

```bash
export TARGON_API_KEY=your-targon-key
python deploy/miner.py --competition clue --model "microsoft/Phi-4-mini-reasoning" --wallet test_miner_0 --hotkey h0
```

If you also want to serve the other role, run the deploy again with `--competition guess`. Use `--sglang-extra-args` if your model needs extra SGLang flags.
