package config

import "fmt"

// Config file constants (searched in this order)
var (
	// SupportedLlamaFarmConfigFiles lists all supported llamafarm config file names
	SupportedLlamaFarmConfigFiles = []string{
		"llamafarm.yaml",
		"llamafarm.yml",
		"llamafarm.toml",
		"llamafarm.json",
	}
)

// LlamaFarmConfig represents the complete llamafarm configuration
type LlamaFarmConfig struct {
	Version   string    `yaml:"version" toml:"version"`
	Name      string    `yaml:"name,omitempty" toml:"name,omitempty"`
	Namespace string    `yaml:"namespace,omitempty" toml:"namespace,omitempty"`
	Prompts   []Prompt  `yaml:"prompts,omitempty" toml:"prompts,omitempty"`
	RAG       RAGConfig `yaml:"rag,omitempty" toml:"rag,omitempty"`
	Datasets  []Dataset `yaml:"datasets,omitempty" toml:"datasets,omitempty"`
	Runtime   *RuntimeConfig     `yaml:"runtime,omitempty" toml:"runtime,omitempty"`
	Models    []ModelDefinition  `yaml:"models,omitempty" toml:"models,omitempty"`
}

// Dataset represents a dataset configuration
type Dataset struct {
	Name   string   `yaml:"name" toml:"name"`
	Parser string   `yaml:"parser,omitempty" toml:"parser,omitempty"`
	Files  []string `yaml:"files" toml:"files"`
}

// Prompt represents a prompt configuration
type Prompt struct {
	Name        string `yaml:"name,omitempty" toml:"name,omitempty"`
	Prompt      string `yaml:"prompt" toml:"prompt"`
	Description string `yaml:"description,omitempty" toml:"description,omitempty"`
}

// RAGConfig represents the RAG configuration
type RAGConfig struct {
	Description         string                             `yaml:"description,omitempty" toml:"description,omitempty"`
	Parsers             map[string]ParserConfig            `yaml:"parsers,omitempty" toml:"parsers,omitempty"`
	Embedders           map[string]EmbedderConfig          `yaml:"embedders,omitempty" toml:"embedders,omitempty"`
	VectorStores        map[string]VectorStoreConfig       `yaml:"vector_stores,omitempty" toml:"vector_stores,omitempty"`
	RetrievalStrategies map[string]RetrievalStrategyConfig `yaml:"retrieval_strategies,omitempty" toml:"retrieval_strategies,omitempty"`
	Defaults            DefaultsConfig                     `yaml:"defaults,omitempty" toml:"defaults,omitempty"`

	// Legacy fields for backwards compatibility
	Parser      ParserConfig      `yaml:"parser,omitempty" toml:"parser,omitempty"`
	Embedder    EmbedderConfig    `yaml:"embedder,omitempty" toml:"embedder,omitempty"`
	VectorStore VectorStoreConfig `yaml:"vector_store,omitempty" toml:"vector_store,omitempty"`
}

// ParserConfig represents a parser configuration
type ParserConfig struct {
	Type           string                 `yaml:"type" toml:"type"`
	Config         map[string]interface{} `yaml:"config,omitempty" toml:"config,omitempty"`
	FileExtensions []string               `yaml:"file_extensions,omitempty" toml:"file_extensions,omitempty"`
	MimeTypes      []string               `yaml:"mime_types,omitempty" toml:"mime_types,omitempty"`
	Priority       int                    `yaml:"priority,omitempty" toml:"priority,omitempty"`
}

// EmbedderConfig represents an embedder configuration
type EmbedderConfig struct {
	Type   string                 `yaml:"type" toml:"type"`
	Config map[string]interface{} `yaml:"config,omitempty" toml:"config,omitempty"`
}

// VectorStoreConfig represents a vector store configuration
type VectorStoreConfig struct {
	Type   string                 `yaml:"type" toml:"type"`
	Config map[string]interface{} `yaml:"config,omitempty" toml:"config,omitempty"`
}

// RetrievalStrategyConfig represents a retrieval strategy configuration
type RetrievalStrategyConfig struct {
	Type        string                 `yaml:"type" toml:"type"`
	Config      map[string]interface{} `yaml:"config,omitempty" toml:"config,omitempty"`
	Description string                 `yaml:"description,omitempty" toml:"description,omitempty"`
}

// DefaultsConfig represents default component selections
type DefaultsConfig struct {
	Parser            string `yaml:"parser" toml:"parser"`
	Embedder          string `yaml:"embedder" toml:"embedder"`
	VectorStore       string `yaml:"vector_store" toml:"vector_store"`
	RetrievalStrategy string `yaml:"retrieval_strategy" toml:"retrieval_strategy"`
}

// RuntimeConfig represents the legacy single-runtime configuration
type RuntimeConfig struct {
	Provider          string                 `yaml:"provider" toml:"provider"`
	Model             string                 `yaml:"model" toml:"model"`
	BaseURL           string                 `yaml:"base_url,omitempty" toml:"base_url,omitempty"`
	APIKey            string                 `yaml:"api_key,omitempty" toml:"api_key,omitempty"`
	InstructorMode    string                 `yaml:"instructor_mode,omitempty" toml:"instructor_mode,omitempty"`
	AgentHandler      string                 `yaml:"agent_handler,omitempty" toml:"agent_handler,omitempty"`
	ModelAPIParameters map[string]interface{} `yaml:"model_api_parameters,omitempty" toml:"model_api_parameters,omitempty"`
}

// ModelDefinition represents a configured model entry
type ModelDefinition struct {
	Alias             string                 `yaml:"alias" toml:"alias"`
	DisplayName       string                 `yaml:"display_name,omitempty" toml:"display_name,omitempty"`
	Description       string                 `yaml:"description,omitempty" toml:"description,omitempty"`
	Provider          string                 `yaml:"provider" toml:"provider"`
	Model             string                 `yaml:"model" toml:"model"`
	BaseURL           string                 `yaml:"base_url,omitempty" toml:"base_url,omitempty"`
	APIKey            string                 `yaml:"api_key,omitempty" toml:"api_key,omitempty"`
	InstructorMode    string                 `yaml:"instructor_mode,omitempty" toml:"instructor_mode,omitempty"`
	AgentHandler      string                 `yaml:"agent_handler,omitempty" toml:"agent_handler,omitempty"`
	Default           bool                   `yaml:"default,omitempty" toml:"default,omitempty"`
	ModelAPIParameters map[string]interface{} `yaml:"model_api_parameters,omitempty" toml:"model_api_parameters,omitempty"`
}

// EffectiveModels returns the configured models, falling back to the legacy runtime when necessary.
func (c *LlamaFarmConfig) EffectiveModels() []ModelDefinition {
	models := make([]ModelDefinition, 0, len(c.Models)+1)
	for _, m := range c.Models {
		models = append(models, m)
	}
	if c.Runtime != nil {
		alias := "runtime"
		if len(models) == 0 {
			alias = "default"
		}
		runtimeModel := ModelDefinition{
			Alias:             alias,
			Provider:          c.Runtime.Provider,
			Model:             c.Runtime.Model,
			BaseURL:           c.Runtime.BaseURL,
			APIKey:            c.Runtime.APIKey,
			InstructorMode:    c.Runtime.InstructorMode,
			AgentHandler:      c.Runtime.AgentHandler,
			Default:           len(models) == 0,
			ModelAPIParameters: copyMap(c.Runtime.ModelAPIParameters),
		}
		models = append(models, runtimeModel)
	}
	if len(models) > 0 && !hasDefaultModel(models) {
		models[0].Default = true
	}
	return models
}

// ResolveModel returns the model definition matching the alias (or provider model name). Empty alias resolves to the default model.
func (c *LlamaFarmConfig) ResolveModel(alias string) (*ModelDefinition, error) {
	models := c.EffectiveModels()
	if len(models) == 0 {
		return nil, fmt.Errorf("no models configured")
	}
	if alias != "" {
		for i := range models {
			if models[i].Alias == alias || models[i].Model == alias {
				return &models[i], nil
			}
		}
		return nil, fmt.Errorf("unknown model alias '%s'", alias)
	}
	for i := range models {
		if models[i].Default {
			return &models[i], nil
		}
	}
	return &models[0], nil
}

// DefaultModelAlias returns the alias of the default model.
func (c *LlamaFarmConfig) DefaultModelAlias() (string, error) {
	model, err := c.ResolveModel("")
	if err != nil {
		return "", err
	}
	return model.Alias, nil
}

func hasDefaultModel(models []ModelDefinition) bool {
	for _, m := range models {
		if m.Default {
			return true
		}
	}
	return false
}

func copyMap(src map[string]interface{}) map[string]interface{} {
	if src == nil {
		return nil
	}
	dst := make(map[string]interface{}, len(src))
	for k, v := range src {
		dst[k] = v
	}
	return dst
}
