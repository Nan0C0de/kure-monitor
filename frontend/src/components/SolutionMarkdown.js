import React, { useState } from 'react';
import { Copy, Check } from 'lucide-react';
import ReactMarkdown from 'react-markdown';

// Code block component with copy button - defined as standalone component
const CodeBlock = ({ code, language }) => {
  const [copied, setCopied] = useState(false);

  const handleCopy = async () => {
    try {
      await navigator.clipboard.writeText(code);
      setCopied(true);
      setTimeout(() => setCopied(false), 2000);
    } catch (err) {
      console.error('Failed to copy:', err);
    }
  };

  return (
    <div className="relative group my-3">
      {language && (
        <div className="absolute top-0 left-0 px-2 py-1 text-xs text-gray-400 bg-gray-700 rounded-tl rounded-br">
          {language}
        </div>
      )}
      <button
        onClick={handleCopy}
        className="absolute top-2 right-2 p-1.5 rounded bg-gray-700 hover:bg-gray-600 text-gray-300 opacity-0 group-hover:opacity-100 transition-opacity"
        title="Copy code"
      >
        {copied ? <Check className="w-4 h-4 text-green-400" /> : <Copy className="w-4 h-4" />}
      </button>
      <pre className="bg-gray-800 text-gray-100 p-4 pt-8 rounded overflow-x-auto text-xs leading-relaxed whitespace-pre-wrap break-words">
        <code>{code}</code>
      </pre>
    </div>
  );
};

const SolutionMarkdown = ({ content, isDark = false }) => {
  return (
    <ReactMarkdown
      components={{
        // Handle pre/code blocks
        pre: ({ children }) => {
          // In react-markdown v9, child.type is the custom component function, not 'code'
          const codeChild = React.Children.toArray(children).find(
            child => React.isValidElement(child)
          );
          if (codeChild) {
            const className = codeChild.props.className || '';
            const language = className.replace('language-', '');
            const codeText = String(codeChild.props.children || '').replace(/\n$/, '');
            return <CodeBlock code={codeText} language={language} />;
          }
          return <pre className="bg-gray-800 text-gray-100 p-4 rounded overflow-x-auto text-xs my-3">{children}</pre>;
        },
        // Inline code as bold, block code passes through for pre handler
        code: ({ className, children, node, ...props }) => {
          // In react-markdown v9, the 'inline' prop is removed.
          // Block code (inside <pre>) has a parent node of type 'element' with tagName 'pre'.
          const isInline = !(node?.properties?.className) &&
            node?.position?.start?.line === node?.position?.end?.line &&
            !className;
          if (isInline) {
            return <strong className={`font-semibold ${isDark ? 'text-gray-100' : 'text-gray-900'}`}>{children}</strong>;
          }
          return <code className={className || ''}>{children}</code>;
        },
        // Style other elements
        p: ({ children }) => <p className={`my-2 ${isDark ? 'text-gray-300' : 'text-gray-700'}`}>{children}</p>,
        h1: ({ children }) => <h1 className={`text-lg font-bold mt-4 mb-2 ${isDark ? 'text-gray-100' : 'text-gray-900'}`}>{children}</h1>,
        h2: ({ children }) => <h2 className={`text-base font-bold mt-4 mb-2 ${isDark ? 'text-gray-100' : 'text-gray-900'}`}>{children}</h2>,
        h3: ({ children }) => <h3 className={`text-sm font-bold mt-3 mb-2 ${isDark ? 'text-gray-100' : 'text-gray-900'}`}>{children}</h3>,
        ul: ({ children }) => <ul className="list-disc list-inside my-2 space-y-1">{children}</ul>,
        ol: ({ children }) => <ol className="list-decimal list-inside my-2 space-y-1">{children}</ol>,
        li: ({ children }) => <li className={isDark ? 'text-gray-300' : 'text-gray-700'}>{children}</li>,
        strong: ({ children }) => <strong className={`font-semibold ${isDark ? 'text-gray-100' : 'text-gray-900'}`}>{children}</strong>,
        a: ({ href, children }) => <a href={href} className={`hover:underline ${isDark ? 'text-blue-400' : 'text-blue-600'}`}>{children}</a>,
      }}
    >
      {content}
    </ReactMarkdown>
  );
};

export default SolutionMarkdown;
