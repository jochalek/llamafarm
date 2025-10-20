package cmd

import (
	"encoding/json"
	"fmt"
	"io"
	"net/http"
	"os"
	"text/tabwriter"

	"llamafarm-cli/cmd/config"

	"github.com/spf13/cobra"
)

var (
	keepData bool // For soft delete
)

// databasesCmd represents the databases command
var databasesCmd = &cobra.Command{
	Use:   "databases",
	Short: "Manage RAG databases in your LlamaFarm configuration",
	Long: `Manage RAG databases on your LlamaFarm server. Databases are vector stores
that hold your embeddings and enable semantic search.

Each database must specify:
  - A database type (e.g., ChromaStore)
  - Configuration (collection name, port, etc.)
  - Embedding strategies
  - Retrieval strategies

Available commands:
  list    - List all databases for a project
  delete  - Delete a database (soft delete keeps data, hard delete removes everything)
  clear   - Clear database data but keep configuration`,
	Run: func(cmd *cobra.Command, args []string) {
		fmt.Println("LlamaFarm Databases Management")
		cmd.Help()
	},
}

// ==== API types (mirroring server) ====
type apiRetrievalStrategy struct {
	Name      string `json:"name"`
	Type      string `json:"type"`
	IsDefault bool   `json:"is_default"`
}

type apiDatabase struct {
	Name                string                  `json:"name"`
	Type                string                  `json:"type"`
	IsDefault           bool                    `json:"is_default"`
	RetrievalStrategies []apiRetrievalStrategy  `json:"retrieval_strategies"`
}

type listDatabasesResponse struct {
	Databases       []apiDatabase `json:"databases"`
	DefaultDatabase *string       `json:"default_database"`
}

type deleteDatabaseResponse struct {
	Database apiDatabase `json:"database"`
	Message  string      `json:"message"`
}

type clearDatabaseResponse struct {
	Database apiDatabase `json:"database"`
	Message  string      `json:"message"`
}

// databasesListCmd represents the databases list command
var databasesListCmd = &cobra.Command{
	Use:     "list",
	Aliases: []string{"ls"},
	Short:   "List all databases for the selected project",
	Long:    `Lists RAG databases from the LlamaFarm server scoped by namespace/project.`,
	Run: func(cmd *cobra.Command, args []string) {
		// Start config watcher for this command
		StartConfigWatcherForCommand()

		// Resolve server and routing
		serverCfg, err := config.GetServerConfig(getEffectiveCWD(), serverURL, namespace, projectID)
		if err != nil {
			fmt.Fprintf(os.Stderr, "Error: %v\n", err)
			os.Exit(1)
		}

		// Ensure server is up (auto-start locally if needed)
		config := ServerOnlyConfig(serverCfg.URL)
		EnsureServicesWithConfig(config)

		url := buildServerURL(serverCfg.URL, fmt.Sprintf("/v1/projects/%s/%s/rag/databases", serverCfg.Namespace, serverCfg.Project))
		req, err := http.NewRequest("GET", url, nil)
		if err != nil {
			fmt.Fprintf(os.Stderr, "Error creating request: %v\n", err)
			os.Exit(1)
		}
		resp, err := getHTTPClient().Do(req)
		if err != nil {
			fmt.Fprintf(os.Stderr, "Error sending request: %v\n", err)
			os.Exit(1)
		}
		defer resp.Body.Close()
		body, readErr := io.ReadAll(resp.Body)
		if resp.StatusCode != http.StatusOK {
			if readErr != nil {
				fmt.Fprintf(os.Stderr, "Error (%d), and body read failed: %v\n", resp.StatusCode, readErr)
				os.Exit(1)
			}
			fmt.Fprintf(os.Stderr, "Error (%d): %s\n", resp.StatusCode, prettyServerError(resp, body))
			os.Exit(1)
		}

		var out listDatabasesResponse
		if err := json.Unmarshal(body, &out); err != nil {
			fmt.Fprintf(os.Stderr, "Failed parsing response: %v\n", err)
			os.Exit(1)
		}

		if len(out.Databases) == 0 {
			fmt.Println("No databases found.")
			return
		}

		fmt.Printf("Found %d database(s):\n\n", len(out.Databases))
		w := tabwriter.NewWriter(os.Stdout, 0, 0, 3, ' ', 0)
		fmt.Fprintln(w, "NAME\tTYPE\tDEFAULT\tSTRATEGIES")
		fmt.Fprintln(w, "----\t----\t-------\t----------")
		for _, db := range out.Databases {
			defaultMark := ""
			if db.IsDefault {
				defaultMark = "✓"
			}
			strategyCount := len(db.RetrievalStrategies)
			fmt.Fprintf(w, "%s\t%s\t%s\t%d\n", db.Name, db.Type, defaultMark, strategyCount)
		}
		w.Flush()

		if out.DefaultDatabase != nil && *out.DefaultDatabase != "" {
			fmt.Printf("\nDefault database: %s\n", *out.DefaultDatabase)
		}
	},
}

// databasesDeleteCmd represents the databases delete command
var databasesDeleteCmd = &cobra.Command{
	Use:     "delete [name]",
	Aliases: []string{"rm", "remove", "del"},
	Short:   "Delete a database from the server",
	Long: `Deletes a database from the LlamaFarm server for the selected project.

By default, this is a SOFT DELETE: the database is removed from llamafarm.yaml
but the data is preserved on disk. This allows you to re-add the database later
and repopulate it.

Use --delete-data for a HARD DELETE that removes both the configuration and all
data from disk. This is permanent and cannot be undone.

Examples:
  lf databases delete main_database                  # Soft delete (keeps data)
  lf databases delete main_database --delete-data    # Hard delete (removes everything)`,
	Args: cobra.ExactArgs(1),
	Run: func(cmd *cobra.Command, args []string) {
		// Start config watcher for this command
		StartConfigWatcherForCommand()

		serverCfg, err := config.GetServerConfig(getEffectiveCWD(), serverURL, namespace, projectID)
		if err != nil {
			fmt.Fprintf(os.Stderr, "Error: %v\n", err)
			os.Exit(1)
		}
		databaseName := args[0]

		// Ensure server is up
		config := ServerOnlyConfig(serverCfg.URL)
		EnsureServicesWithConfig(config)

		// Build URL with delete_data query parameter
		deleteData := !keepData // Invert: keepData=false means deleteData=true
		url := buildServerURL(serverCfg.URL, fmt.Sprintf("/v1/projects/%s/%s/rag/databases/%s?delete_data=%t",
			serverCfg.Namespace, serverCfg.Project, databaseName, deleteData))

		req, err := http.NewRequest("DELETE", url, nil)
		if err != nil {
			fmt.Fprintf(os.Stderr, "Error creating request: %v\n", err)
			os.Exit(1)
		}
		resp, err := getHTTPClient().Do(req)
		if err != nil {
			fmt.Fprintf(os.Stderr, "Error sending request: %v\n", err)
			os.Exit(1)
		}
		defer resp.Body.Close()
		body, readErr := io.ReadAll(resp.Body)
		if resp.StatusCode != http.StatusOK {
			if readErr != nil {
				fmt.Fprintf(os.Stderr, "Failed to delete database '%s' (%d), and body read failed: %v\n", databaseName, resp.StatusCode, readErr)
				os.Exit(1)
			}
			fmt.Fprintf(os.Stderr, "Failed to delete database '%s' (%d): %s\n", databaseName, resp.StatusCode, prettyServerError(resp, body))
			os.Exit(1)
		}

		var result deleteDatabaseResponse
		if err := json.Unmarshal(body, &result); err != nil {
			fmt.Fprintf(os.Stderr, "Failed parsing response: %v\n", err)
			os.Exit(1)
		}

		fmt.Printf("✅ %s\n", result.Message)
	},
}

// databasesClearCmd represents the databases clear command
var databasesClearCmd = &cobra.Command{
	Use:   "clear [name]",
	Short: "Clear all data from a database but keep its configuration",
	Long: `Clears all data from a database but keeps it in the llamafarm.yaml configuration.

This is useful when you want to repopulate a database from scratch without
reconfiguring embedding strategies, retrieval strategies, etc.

Examples:
  lf databases clear main_database`,
	Args: cobra.ExactArgs(1),
	Run: func(cmd *cobra.Command, args []string) {
		// Start config watcher for this command
		StartConfigWatcherForCommand()

		serverCfg, err := config.GetServerConfig(getEffectiveCWD(), serverURL, namespace, projectID)
		if err != nil {
			fmt.Fprintf(os.Stderr, "Error: %v\n", err)
			os.Exit(1)
		}
		databaseName := args[0]

		// Ensure server is up
		config := ServerOnlyConfig(serverCfg.URL)
		EnsureServicesWithConfig(config)

		url := buildServerURL(serverCfg.URL, fmt.Sprintf("/v1/projects/%s/%s/rag/databases/%s/clear",
			serverCfg.Namespace, serverCfg.Project, databaseName))

		req, err := http.NewRequest("POST", url, nil)
		if err != nil {
			fmt.Fprintf(os.Stderr, "Error creating request: %v\n", err)
			os.Exit(1)
		}
		resp, err := getHTTPClient().Do(req)
		if err != nil {
			fmt.Fprintf(os.Stderr, "Error sending request: %v\n", err)
			os.Exit(1)
		}
		defer resp.Body.Close()
		body, readErr := io.ReadAll(resp.Body)
		if resp.StatusCode != http.StatusOK {
			if readErr != nil {
				fmt.Fprintf(os.Stderr, "Failed to clear database '%s' (%d), and body read failed: %v\n", databaseName, resp.StatusCode, readErr)
				os.Exit(1)
			}
			fmt.Fprintf(os.Stderr, "Failed to clear database '%s' (%d): %s\n", databaseName, resp.StatusCode, prettyServerError(resp, body))
			os.Exit(1)
		}

		var result clearDatabaseResponse
		if err := json.Unmarshal(body, &result); err != nil {
			fmt.Fprintf(os.Stderr, "Failed parsing response: %v\n", err)
			os.Exit(1)
		}

		fmt.Printf("✅ %s\n", result.Message)
	},
}

func init() {
	// Server routing flags (align with datasets)
	databasesCmd.PersistentFlags().StringVar(&serverURL, "server-url", "", "LlamaFarm server URL (default: http://localhost:8000)")
	databasesCmd.PersistentFlags().StringVar(&namespace, "namespace", "", "Project namespace (default: from llamafarm.yaml)")
	databasesCmd.PersistentFlags().StringVar(&projectID, "project", "", "Project ID (default: from llamafarm.yaml)")

	// Delete flags
	databasesDeleteCmd.Flags().BoolVar(&keepData, "keep-data", false, "Keep database data on disk (soft delete)")

	// Add subcommands to databases
	databasesCmd.AddCommand(databasesListCmd)
	databasesCmd.AddCommand(databasesDeleteCmd)
	databasesCmd.AddCommand(databasesClearCmd)

	// Add the databases command to root
	rootCmd.AddCommand(databasesCmd)
}
