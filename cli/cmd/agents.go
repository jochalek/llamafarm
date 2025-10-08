package cmd

import (
	"bytes"
	"encoding/json"
	"fmt"
	"io"
	"net/http"
	"os"
	"strings"

	"llamafarm-cli/cmd/config"

	"github.com/spf13/cobra"
)

// agentsCmd represents the agents command namespace
var agentsCmd = &cobra.Command{
	Use:   "agents",
	Short: "Manage and run agents",
	Long: `Manage and execute agents configured in LlamaFarm.

Agents are autonomous entities that can analyze documents, validate RAG responses,
generate reports, and orchestrate complex workflows.`,
	Hidden: false,
	Run: func(cmd *cobra.Command, args []string) {
		fmt.Println("LlamaFarm Agents Management")
		cmd.Help()
	},
}

// Agent response types
type AgentInfo struct {
	Name        string   `json:"name"`
	Type        string   `json:"type"`
	Description string   `json:"description,omitempty"`
	Model       string   `json:"model,omitempty"`
	Tools       []string `json:"tools,omitempty"`
}

type ListAgentsResponse struct {
	Total  int         `json:"total"`
	Agents []AgentInfo `json:"agents"`
}

type AgentRunRequest struct {
	Input      interface{}            `json:"input"`
	Parameters map[string]interface{} `json:"parameters,omitempty"`
	Stream     bool                   `json:"stream"`
}

type AgentRunResponse struct {
	AgentName string      `json:"agent_name"`
	Status    string      `json:"status"`
	Result    interface{} `json:"result,omitempty"`
	Error     string      `json:"error,omitempty"`
}

var agentsListCmd = &cobra.Command{
	Use:   "list [namespace/project]",
	Short: "List configured agents",
	Long: `List all agents configured in a LlamaFarm project.

Examples:
  # List agents for explicit project
  lf agents list my-org/my-project

  # List agents from current directory config
  lf agents list`,
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
		config := ChatNoRAGConfig(serverURL)
		EnsureServicesWithConfig(config)

		// Fetch agents from API
		url := fmt.Sprintf("%s/v1/projects/%s/%s/agents", serverURL, ns, proj)
		resp, err := http.Get(url)
		if err != nil {
			fmt.Fprintf(os.Stderr, "Error fetching agents: %v\n", err)
			os.Exit(1)
		}
		defer resp.Body.Close()

		if resp.StatusCode != http.StatusOK {
			body, _ := io.ReadAll(resp.Body)
			fmt.Fprintf(os.Stderr, "Error: Server returned %d: %s\n", resp.StatusCode, string(body))
			os.Exit(1)
		}

		var agentsResp ListAgentsResponse
		if err := json.NewDecoder(resp.Body).Decode(&agentsResp); err != nil {
			fmt.Fprintf(os.Stderr, "Error decoding response: %v\n", err)
			os.Exit(1)
		}

		if agentsResp.Total == 0 {
			fmt.Println("No agents configured")
			return
		}

		fmt.Printf("Agents for %s/%s:\n\n", ns, proj)
		for _, agent := range agentsResp.Agents {
			fmt.Printf("  • %s (%s)\n", agent.Name, agent.Type)
			if agent.Description != "" {
				fmt.Printf("    %s\n", agent.Description)
			}
			if agent.Model != "" {
				fmt.Printf("    Model: %s\n", agent.Model)
			}
			if len(agent.Tools) > 0 {
				fmt.Printf("    Tools: %s\n", strings.Join(agent.Tools, ", "))
			}
			fmt.Println()
		}
	},
}

var (
	agentInputJSON   string
	agentInputFile   string
	agentParams      []string
	agentStream      bool
	agentOutputFile  string
	agentOutputJSON  bool
)

var agentsRunCmd = &cobra.Command{
	Use:   "run <agent_name> [namespace/project]",
	Short: "Run an agent",
	Long: `Execute an agent with the provided input.

Examples:
  # Run agent with JSON input
  lf agents run my_agent --input '{"text": "hello"}'

  # Run agent with file input
  lf agents run my_agent --input-file data.json

  # Run agent with streaming
  lf agents run my_agent --input '{"query": "test"}' --stream

  # Run agent and save output to file
  lf agents run my_agent --input '{}' --output report.json`,
	Args: cobra.MinimumNArgs(1),
	Run: func(cmd *cobra.Command, args []string) {
		agentName := args[0]
		var ns, proj string

		// Parse explicit project if provided
		if len(args) >= 2 && strings.Contains(args[1], "/") {
			parts := strings.SplitN(args[1], "/", 2)
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
		config := ChatNoRAGConfig(serverURL)
		EnsureServicesWithConfig(config)

		// Parse input
		var input interface{}
		if agentInputFile != "" {
			data, err := os.ReadFile(agentInputFile)
			if err != nil {
				fmt.Fprintf(os.Stderr, "Error reading input file: %v\n", err)
				os.Exit(1)
			}
			if err := json.Unmarshal(data, &input); err != nil {
				fmt.Fprintf(os.Stderr, "Error parsing input file: %v\n", err)
				os.Exit(1)
			}
		} else if agentInputJSON != "" {
			if err := json.Unmarshal([]byte(agentInputJSON), &input); err != nil {
				fmt.Fprintf(os.Stderr, "Error parsing input JSON: %v\n", err)
				os.Exit(1)
			}
		} else {
			input = map[string]interface{}{}
		}

		// Parse parameters
		params := make(map[string]interface{})
		for _, p := range agentParams {
			parts := strings.SplitN(p, "=", 2)
			if len(parts) == 2 {
				params[parts[0]] = parts[1]
			}
		}

		// Create request
		reqBody := AgentRunRequest{
			Input:      input,
			Parameters: params,
			Stream:     agentStream,
		}

		reqData, err := json.Marshal(reqBody)
		if err != nil {
			fmt.Fprintf(os.Stderr, "Error creating request: %v\n", err)
			os.Exit(1)
		}

		// Execute agent
		url := fmt.Sprintf("%s/v1/projects/%s/%s/agents/%s/run", serverURL, ns, proj, agentName)
		resp, err := http.Post(url, "application/json", bytes.NewReader(reqData))
		if err != nil {
			fmt.Fprintf(os.Stderr, "Error running agent: %v\n", err)
			os.Exit(1)
		}
		defer resp.Body.Close()

		if resp.StatusCode != http.StatusOK {
			body, _ := io.ReadAll(resp.Body)
			fmt.Fprintf(os.Stderr, "Error: Server returned %d: %s\n", resp.StatusCode, string(body))
			os.Exit(1)
		}

		// Handle response
		body, err := io.ReadAll(resp.Body)
		if err != nil {
			fmt.Fprintf(os.Stderr, "Error reading response: %v\n", err)
			os.Exit(1)
		}

		// Save to file if specified
		if agentOutputFile != "" {
			if err := os.WriteFile(agentOutputFile, body, 0644); err != nil {
				fmt.Fprintf(os.Stderr, "Error writing output file: %v\n", err)
				os.Exit(1)
			}
			fmt.Printf("Output saved to %s\n", agentOutputFile)
			return
		}

		// Parse and display response
		var runResp AgentRunResponse
		if err := json.Unmarshal(body, &runResp); err != nil {
			// Not JSON, just print raw
			fmt.Println(string(body))
			return
		}

		if runResp.Status == "failed" {
			fmt.Fprintf(os.Stderr, "Agent execution failed: %s\n", runResp.Error)
			os.Exit(1)
		}

		// Print result
		if agentOutputJSON {
			resultJSON, _ := json.MarshalIndent(runResp.Result, "", "  ")
			fmt.Println(string(resultJSON))
		} else {
			fmt.Println("\nAgent Result:")
			fmt.Println("=============")
			resultJSON, _ := json.MarshalIndent(runResp.Result, "", "  ")
			fmt.Println(string(resultJSON))
		}
	},
}

var agentsInspectCmd = &cobra.Command{
	Use:   "inspect <agent_name> [namespace/project]",
	Short: "Show agent details",
	Long: `Display detailed information about a specific agent.

Examples:
  # Inspect an agent
  lf agents inspect my_agent

  # Inspect agent from specific project
  lf agents inspect my_agent my-org/my-project`,
	Args: cobra.MinimumNArgs(1),
	Run: func(cmd *cobra.Command, args []string) {
		agentName := args[0]
		var ns, proj string

		// Parse explicit project if provided
		if len(args) >= 2 && strings.Contains(args[1], "/") {
			parts := strings.SplitN(args[1], "/", 2)
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
		config := ChatNoRAGConfig(serverURL)
		EnsureServicesWithConfig(config)

		// Fetch agent details
		url := fmt.Sprintf("%s/v1/projects/%s/%s/agents/%s", serverURL, ns, proj, agentName)
		resp, err := http.Get(url)
		if err != nil {
			fmt.Fprintf(os.Stderr, "Error fetching agent: %v\n", err)
			os.Exit(1)
		}
		defer resp.Body.Close()

		if resp.StatusCode != http.StatusOK {
			body, _ := io.ReadAll(resp.Body)
			fmt.Fprintf(os.Stderr, "Error: Server returned %d: %s\n", resp.StatusCode, string(body))
			os.Exit(1)
		}

		var agent AgentInfo
		if err := json.NewDecoder(resp.Body).Decode(&agent); err != nil {
			fmt.Fprintf(os.Stderr, "Error decoding response: %v\n", err)
			os.Exit(1)
		}

		// Display agent details
		fmt.Printf("Agent: %s\n", agent.Name)
		fmt.Printf("Type: %s\n", agent.Type)
		if agent.Description != "" {
			fmt.Printf("Description: %s\n", agent.Description)
		}
		if agent.Model != "" {
			fmt.Printf("Model: %s\n", agent.Model)
		}
		if len(agent.Tools) > 0 {
			fmt.Printf("Tools: %s\n", strings.Join(agent.Tools, ", "))
		}
	},
}

func init() {
	// Add flags to run command
	agentsRunCmd.Flags().StringVar(&agentInputJSON, "input", "", "Input data as JSON string")
	agentsRunCmd.Flags().StringVar(&agentInputFile, "input-file", "", "Input data from JSON file")
	agentsRunCmd.Flags().StringSliceVar(&agentParams, "param", []string{}, "Additional parameters (key=value)")
	agentsRunCmd.Flags().BoolVar(&agentStream, "stream", false, "Enable streaming output")
	agentsRunCmd.Flags().StringVar(&agentOutputFile, "output", "", "Save output to file")
	agentsRunCmd.Flags().BoolVar(&agentOutputJSON, "json", false, "Output result as JSON only")

	// Add subcommands
	agentsCmd.AddCommand(agentsListCmd)
	agentsCmd.AddCommand(agentsRunCmd)
	agentsCmd.AddCommand(agentsInspectCmd)

	// Register with root
	rootCmd.AddCommand(agentsCmd)
}
