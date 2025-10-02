package cmd

import (
	"fmt"
	"os"
	"path/filepath"
	"strings"

	"llamafarm-cli/cmd/config"

	"github.com/spf13/cobra"
)

var (
	runInputFile         string
	runRAGDatabase       string
	runRetrievalStrategy string
	runRAGTopK           int
	runNoRAG             bool
	runRAGScoreThreshold float64
	runModel             string
	runImagePath         string
	runImageDir          string
)

// chatCmd represents the `lf chat` command
var chatCmd = &cobra.Command{
	Use:   "chat [namespace/project] \"input\"",
	Short: "Chat with a LlamaFarm project (RAG by default)",
	Long: `Chat with a LlamaFarm project.

Examples:
  # Explicit project and inline input
  lf chat my-org/my-project "What models are configured?"

  # Explicit project and input file
  lf chat my-org/my-project -f ./prompt.txt

  # Project inferred from llamafarm.yaml, inline input
  lf chat "What models are configured?"

  # Project inferred from llamafarm.yaml, input file
  lf chat -f ./prompt.txt

  # Chat with RAG (default behavior)
  lf chat "What is transformer architecture?"

  # Run with specific database
  lf chat --database main_database "Explain attention mechanism"

  # Run with custom retrieval strategy and top-k
  lf chat --retrieval-strategy filtered_search --rag-top-k 10 "How do neural networks work?"

  # Run WITHOUT RAG (LLM only)
  lf chat --no-rag "What is machine learning?"

  # Select specific model
  lf chat --model fast "What is machine learning?"

  # Use vision model with an image
  lf chat --model vision --image ./photo.jpg "What's in this image?"

  # Use vision model with multiple images from a directory
  lf chat --model vision --image-dir ./screenshots "Compare these UI designs"`,
	Args: func(cmd *cobra.Command, args []string) error {
		// Valid forms:
		// 1) chat <ns>/<proj> <input>
		// 2) chat <ns>/<proj> --file <path>
		// 3) chat <input>              (ns/proj inferred from config)
		// 4) chat --file <path>        (ns/proj inferred from config)

		if len(args) == 0 {
			// Must at least have input via file
			if runInputFile == "" {
				return fmt.Errorf("provide an input string or --file")
			}
			return nil
		}

		if strings.Contains(args[0], "/") {
			// Explicit project provided
			if strings.Count(args[0], "/") != 1 {
				return fmt.Errorf("project must be in format 'namespace/project', got: %s", args[0])
			}
			// If no file, require inline input as second arg
			if runInputFile == "" && len(args) < 2 {
				return fmt.Errorf("provide an input string or --file")
			}
			// If file is set, do not allow a third arg
			if runInputFile != "" && len(args) >= 2 {
				return fmt.Errorf("specify either --file or an inline input, not both")
			}
			return nil
		}

		// No explicit project; first arg is the inline input.
		// If a file is also provided, it's ambiguous/invalid.
		if runInputFile != "" {
			return fmt.Errorf("specify either --file or an inline input, not both")
		}
		return nil
	},
	Run: func(cmd *cobra.Command, args []string) {
		// Resolve project and input according to args pattern
		var ns, proj string

		// Resolve input
		var input string
		if runInputFile != "" {
			data, err := os.ReadFile(runInputFile)
			if err != nil {
				fmt.Fprintf(os.Stderr, "Error reading file '%s': %v\n", runInputFile, err)
				os.Exit(1)
			}
			input = string(data)
		} else if len(args) >= 1 {
			if strings.Contains(args[0], "/") {
				// Explicit project, inline input follows
				if len(args) >= 2 {
					input = args[1]
				}
			} else {
				// No explicit project, first arg is inline input
				input = args[0]
			}
		}

		// Parse explicit project if provided
		if len(args) >= 1 && strings.Contains(args[0], "/") {
			parts := strings.SplitN(args[0], "/", 2)
			ns = strings.TrimSpace(parts[0])
			proj = strings.TrimSpace(parts[1])
		}

		cwd := getEffectiveCWD()

		StartConfigWatcherForCommand()

		// Resolve server configuration (strict): if ns/proj are absent, require from llamafarm.yaml
		serverCfg, err := config.GetServerConfig(cwd, serverURL, ns, proj)
		if err != nil {
			fmt.Fprintf(os.Stderr, "Error: %v\n", err)
			os.Exit(1)
		}
		serverURL = serverCfg.URL
		ns = serverCfg.Namespace
		proj = serverCfg.Project

		// Ensure server is up (auto-start locally if needed)
		ensureServerAvailable(serverURL, true)

		// Construct context and call the project-scoped chat completions via shared helpers
		ctx := &ChatSessionContext{
			ServerURL:        serverURL,
			Namespace:        ns,
			ProjectID:        proj,
			SessionMode:      SessionModeStateless,
			SessionNamespace: ns,
			SessionProject:   proj,
			Temperature:      temperature,
			MaxTokens:        maxTokens,
			HTTPClient:       getHTTPClient(),
			Model:            runModel,
			// RAG settings - RAG is enabled by default unless --no-rag is used
			RAGEnabled:           !runNoRAG,
			RAGDatabase:          runRAGDatabase,
			RAGRetrievalStrategy: runRetrievalStrategy,
			RAGTopK:              runRAGTopK,
			RAGScoreThreshold:    runRAGScoreThreshold,
		}

		// Collect image paths
		var imagePaths []string
		if runImagePath != "" {
			imagePaths = append(imagePaths, runImagePath)
		}
		if runImageDir != "" {
			// Read all image files from directory
			entries, err := os.ReadDir(runImageDir)
			if err != nil {
				fmt.Fprintf(os.Stderr, "Error reading image directory '%s': %v\n", runImageDir, err)
				os.Exit(1)
			}
			for _, entry := range entries {
				if !entry.IsDir() {
					ext := strings.ToLower(filepath.Ext(entry.Name()))
					if ext == ".jpg" || ext == ".jpeg" || ext == ".png" || ext == ".gif" || ext == ".webp" {
						imagePaths = append(imagePaths, filepath.Join(runImageDir, entry.Name()))
					}
				}
			}
		}

		// Create message (vision if images present)
		var userMsg ChatMessage
		if len(imagePaths) > 0 {
			// Limit to 10 images per OpenAI spec
			if len(imagePaths) > 10 {
				fmt.Fprintf(os.Stderr, "Warning: More than 10 images provided, using first 10\n")
				imagePaths = imagePaths[:10]
			}

			visionMsg, err := createVisionMessage(input, imagePaths)
			if err != nil {
				fmt.Fprintf(os.Stderr, "Error creating vision message: %v\n", err)
				os.Exit(1)
			}
			userMsg = visionMsg
		} else {
			userMsg = ChatMessage{Role: "user", Content: input}
		}

		messages := []ChatMessage{userMsg}
		resp, err := sendChatRequest(messages, ctx)
		if err != nil {
			fmt.Fprintf(os.Stderr, "Error: %v\n", err)
			os.Exit(1)
		}
		if resp == "" {
			fmt.Printf("No response received\n")
		} else {
			fmt.Printf("%s\n", resp)
		}
	},
}

func init() {
	chatCmd.Flags().StringVarP(&runInputFile, "file", "f", "", "path to file containing input text")

	chatCmd.Flags().StringVar(&runModel, "model", "", "Model to use for the request (default: from config)")
	chatCmd.Flags().BoolVar(&runNoRAG, "no-rag", false, "Disable RAG (use LLM only without document retrieval)")
	chatCmd.Flags().StringVar(&runRAGDatabase, "database", "", "Database to use for RAG (default: from config)")
	chatCmd.Flags().StringVar(&runRetrievalStrategy, "retrieval-strategy", "", "Retrieval strategy to use (default: from database config)")
	chatCmd.Flags().IntVar(&runRAGTopK, "rag-top-k", 5, "Number of RAG results to retrieve")
	chatCmd.Flags().Float64Var(&runRAGScoreThreshold, "rag-score-threshold", 0.0, "Minimum score threshold for RAG results")

	// Vision support flags
	chatCmd.Flags().StringVar(&runImagePath, "image", "", "Path to an image file for vision models (jpg, png, gif, webp)")
	chatCmd.Flags().StringVar(&runImageDir, "image-dir", "", "Path to directory containing images (processes all images, max 10)")

	rootCmd.AddCommand(chatCmd)
}
