// Offline rendering helper for the Go-template functions used by these ApplicationSets.
// It does not emulate the ApplicationSet controller or Kubernetes admission.
package main

import (
	"bytes"
	"encoding/json"
	"fmt"
	"os"
	"strconv"
	"text/template"
)

type Request struct {
	Value any            `json:"value"`
	Data  map[string]any `json:"data"`
}

func render(v any, data map[string]any) (any, error) {
	switch x := v.(type) {
	case string:
		t, e := template.New("field").Option("missingkey=error").Funcs(template.FuncMap{"quote": func(s string) string { return strconv.Quote(s) }}).Parse(x)
		if e != nil {
			return nil, e
		}
		var b bytes.Buffer
		e = t.Execute(&b, data)
		return b.String(), e
	case []any:
		for i, a := range x {
			b, e := render(a, data)
			if e != nil {
				return nil, e
			}
			x[i] = b
		}
		return x, nil
	case map[string]any:
		for k, a := range x {
			b, e := render(a, data)
			if e != nil {
				return nil, e
			}
			x[k] = b
		}
		return x, nil
	default:
		return v, nil
	}
}
func main() {
	var r Request
	if e := json.NewDecoder(os.Stdin).Decode(&r); e != nil {
		panic(e)
	}
	v, e := render(r.Value, r.Data)
	if e != nil {
		fmt.Fprintln(os.Stderr, e)
		os.Exit(1)
	}
	if e = json.NewEncoder(os.Stdout).Encode(v); e != nil {
		panic(e)
	}
}
