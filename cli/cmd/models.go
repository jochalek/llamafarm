package cmd

import (
	"context"
	"encoding/json"
	"fmt"
	"io"
	"net/http"
	"os"
	"strings"
	"time"

	"llamafarm-cli/cmd/config"

	"github.com/spf13/cobra"
)

// modelsCmd represents the models command namespace
var modelsCmd = &cobra.Command{
	Use:   "models",
	Short: "Manage models and model backends",
	Long: `Manage models, providers, and backends configured in LlamaFarm.

Available commands will include listing models, testing inference, and syncing configs.`,
	Hidden: false,
	Run: func(cmd *cobra.Command, args []string) {
		fmt.Println("LlamaFarm Models Management")
		cmd.Help()
	},
}

var modelsListCmd = &cobra.Command{
	Use:   "list [namespace/project]",
	Short: "List available models for a project",
	Long: `List all configured models for a LlamaFarm project.

Examples:
  # List models for explicit project
  lf models list my-org/my-project

  # List models from current directory config
  lf models list`,
	Run: func(cmd *cobra.Command, args []string) {
		var ns, proj string

		// Parse explicit project if provided
		if len(args) >= 1 && strings.Contains(args[0], "/") {
			parts := strings.SplitN(args[0], "/", 2)
			ns = strings.TrimSpace(parts[0])
			proj = strings.TrimSpace(parts[1])
		}

		cwd := getEffectiveCWD()
		StartConfigWatcherForCommand()

		// Resolve server configuration
		serverCfg, err := config.GetServerConfig(cwd, serverURL, ns, proj)
		if err != nil {
			fmt.Fprintf(os.Stderr, "Error: %v\n", err)
			os.Exit(1)
		}
		serverURL = serverCfg.URL
		ns = serverCfg.Namespace
		proj = serverCfg.Project

		// Ensure server is up
		ensureServerAvailable(serverURL, true)

		// Call API endpoint
		url := fmt.Sprintf("%s/v1/projects/%s/%s/models", strings.TrimSuffix(serverURL, "/"), ns, proj)
		ctx, cancel := context.WithTimeout(context.Background(), 10*time.Second)
		defer cancel()

		req, err := http.NewRequestWithContext(ctx, "GET", url, nil)
		if err != nil {
			fmt.Fprintf(os.Stderr, "Error creating request: %v\n", err)
			os.Exit(1)
		}

		resp, err := getHTTPClient().Do(req)
		if err != nil {
			fmt.Fprintf(os.Stderr, "Error fetching models: %v\n", err)
			os.Exit(1)
		}
		defer resp.Body.Close()

		if resp.StatusCode != http.StatusOK {
			body, _ := io.ReadAll(resp.Body)
			fmt.Fprintf(os.Stderr, "Server error %d: %s\n", resp.StatusCode, string(body))
			os.Exit(1)
		}

		var result struct {
			Models []struct {
				ID          string `json:"id"`
				Description string `json:"description"`
				Provider    string `json:"provider"`
				Model       string `json:"model"`
				IsDefault   bool   `json:"is_default"`
			} `json:"models"`
		}

		if err := json.NewDecoder(resp.Body).Decode(&result); err != nil {
			fmt.Fprintf(os.Stderr, "Error parsing response: %v\n", err)
			os.Exit(1)
		}

		if len(result.Models) == 0 {
			fmt.Println("No models configured")
			return
		}

		fmt.Printf("Models for %s/%s:\n\n", ns, proj)
		for _, m := range result.Models {
			defaultMarker := ""
			if m.IsDefault {
				defaultMarker = " (default)"
			}
			fmt.Printf("  • %s%s\n", m.ID, defaultMarker)
			if m.Description != "" {
				fmt.Printf("    %s\n", m.Description)
			}
			fmt.Printf("    Provider: %s | Model: %s\n", m.Provider, m.Model)
			fmt.Println()
		}
	},
}

var modelsPullCmd = &cobra.Command{
	Use:   "pull MODEL_NAME --provider PROVIDER [flags]",
	Short: "Pull/download a model from a provider",
	Long: `Pull/download a model from a configured provider (Ollama, Lemonade, etc.).

Examples:
  # Pull a model from Ollama
  lf models pull llama3:70b --provider ollama

  # Pull a GGUF model from Lemonade with custom checkpoint
  lf models pull user.gemma-3-4b --provider lemonade --checkpoint google/gemma-3-4b-it-qat-q4_0-gguf --variant Q4_0 --recipe llamacpp

  # Pull a registered Lemonade model
  lf models pull Qwen2.5-VL-7B-Instruct-GGUF --provider lemonade`,
	Args: cobra.ExactArgs(1),
	Run: func(cmd *cobra.Command, args []string) {
		modelName := args[0]

		// Get flags
		provider, _ := cmd.Flags().GetString("provider")
		checkpoint, _ := cmd.Flags().GetString("checkpoint")
		variant, _ := cmd.Flags().GetString("variant")
		recipe, _ := cmd.Flags().GetString("recipe")
		vision, _ := cmd.Flags().GetBool("vision")
		reasoning, _ := cmd.Flags().GetBool("reasoning")
		mmproj, _ := cmd.Flags().GetString("mmproj")
		insecure, _ := cmd.Flags().GetBool("insecure")

		if provider == "" {
			fmt.Fprintf(os.Stderr, "Error: --provider is required\n")
			os.Exit(1)
		}

		var ns, proj string
		projectArg, _ := cmd.Flags().GetString("project")
		if projectArg != "" && strings.Contains(projectArg, "/") {
			parts := strings.SplitN(projectArg, "/", 2)
			ns = strings.TrimSpace(parts[0])
			proj = strings.TrimSpace(parts[1])
		}

		cwd := getEffectiveCWD()
		StartConfigWatcherForCommand()

		// Resolve server configuration
		serverCfg, err := config.GetServerConfig(cwd, serverURL, ns, proj)
		if err != nil {
			fmt.Fprintf(os.Stderr, "Error: %v\n", err)
			os.Exit(1)
		}
		serverURL = serverCfg.URL
		ns = serverCfg.Namespace
		proj = serverCfg.Project

		// Ensure server is up
		ensureServerAvailable(serverURL, true)

		// Build request payload
		payload := map[string]interface{}{
			"model_name": modelName,
			"provider":   provider,
		}

		if checkpoint != "" {
			payload["checkpoint"] = checkpoint
		}
		if variant != "" {
			payload["variant"] = variant
		}
		if recipe != "" {
			payload["recipe"] = recipe
		}
		if vision {
			payload["vision"] = true
		}
		if reasoning {
			payload["reasoning"] = true
		}
		if mmproj != "" {
			payload["mmproj"] = mmproj
		}
		if insecure {
			payload["insecure"] = true
		}

		payloadBytes, err := json.Marshal(payload)
		if err != nil {
			fmt.Fprintf(os.Stderr, "Error creating request: %v\n", err)
			os.Exit(1)
		}

		// Call API endpoint
		url := fmt.Sprintf("%s/v1/models/%s/%s/models/pull", strings.TrimSuffix(serverURL, "/"), ns, proj)
		req, err := http.NewRequest("POST", url, strings.NewReader(string(payloadBytes)))
		if err != nil {
			fmt.Fprintf(os.Stderr, "Error creating request: %v\n", err)
			os.Exit(1)
		}
		req.Header.Set("Content-Type", "application/json")

		fmt.Printf("Pulling model '%s' from %s...\n", modelName, provider)

		resp, err := getHTTPClient().Do(req)
		if err != nil {
			fmt.Fprintf(os.Stderr, "Error pulling model: %v\n", err)
			os.Exit(1)
		}
		defer resp.Body.Close()

		if resp.StatusCode != http.StatusOK {
			body, _ := io.ReadAll(resp.Body)
			fmt.Fprintf(os.Stderr, "Server error %d: %s\n", resp.StatusCode, string(body))
			os.Exit(1)
		}

		// Stream progress updates (NDJSON format)
		decoder := json.NewDecoder(resp.Body)
		for {
			var progress map[string]interface{}
			if err := decoder.Decode(&progress); err != nil {
				if err == io.EOF {
					break
				}
				fmt.Fprintf(os.Stderr, "Error reading progress: %v\n", err)
				break
			}

			status := progress["status"]
			message := progress["message"]

			if status == "error" {
				fmt.Fprintf(os.Stderr, "\n❌ Error: %v\n", message)
				os.Exit(1)
			} else if status == "success" {
				fmt.Printf("\n✓ %v\n", message)
			} else {
				// Progress update
				if message != nil {
					fmt.Printf("\r%v", message)
				}
			}
		}

		fmt.Println("\nModel pull complete!")
	},
}

func init() {
	// Add flags for models pull command
	modelsPullCmd.Flags().String("provider", "", "Provider to pull from (ollama, lemonade, etc.) [required]")
	modelsPullCmd.Flags().String("project", "", "Project in format namespace/project")
	modelsPullCmd.Flags().String("checkpoint", "", "HuggingFace checkpoint for Lemonade custom models")
	modelsPullCmd.Flags().String("variant", "", "Variant/quantization for GGUF models (e.g., Q4_0, Q8_0)")
	modelsPullCmd.Flags().String("recipe", "", "Recipe for Lemonade (llamacpp, transformers, onnx)")
	modelsPullCmd.Flags().Bool("vision", false, "Model supports vision (Lemonade)")
	modelsPullCmd.Flags().Bool("reasoning", false, "Model has reasoning capabilities (Lemonade)")
	modelsPullCmd.Flags().String("mmproj", "", "Multimodal projector file for vision models (Lemonade)")
	modelsPullCmd.Flags().Bool("insecure", false, "Allow insecure connections (Ollama)")

	modelsCmd.AddCommand(modelsListCmd)
	modelsCmd.AddCommand(modelsPullCmd)
	rootCmd.AddCommand(modelsCmd)
}
