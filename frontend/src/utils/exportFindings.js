import { jsPDF } from 'jspdf';
import { applyPlugin } from 'jspdf-autotable';

applyPlugin(jsPDF);

const getDateStamp = () => new Date().toISOString().split('T')[0];

const mapFindings = (findings) =>
  findings.map(f => ({
    severity: f.severity,
    resource_type: f.resource_type,
    resource_name: f.resource_name,
    namespace: f.namespace,
    category: f.category,
    title: f.title,
    description: f.description,
    remediation: f.remediation,
    timestamp: f.timestamp,
  }));

const downloadBlob = (blob, filename) => {
  const url = URL.createObjectURL(blob);
  const a = document.createElement('a');
  a.style.display = 'none';
  a.href = url;
  a.download = filename;
  document.body.appendChild(a);
  a.click();
  document.body.removeChild(a);
  URL.revokeObjectURL(url);
};

const escapeCSV = (value) => {
  const str = String(value ?? '');
  if (str.includes(',') || str.includes('"') || str.includes('\n') || str.includes('\r')) {
    return `"${str.replace(/"/g, '""')}"`;
  }
  return str;
};

export const exportAsCSV = (findings) => {
  const headers = ['Severity', 'Resource Type', 'Resource Name', 'Namespace', 'Category', 'Title', 'Description', 'Remediation', 'Timestamp'];
  const rows = mapFindings(findings).map(f => [
    f.severity, f.resource_type, f.resource_name, f.namespace,
    f.category, f.title, f.description, f.remediation, f.timestamp,
  ]);

  const csv = [
    headers.map(escapeCSV).join(','),
    ...rows.map(row => row.map(escapeCSV).join(','))
  ].join('\n');

  const blob = new Blob([csv], { type: 'text/csv;charset=utf-8;' });
  downloadBlob(blob, `security-findings-${getDateStamp()}.csv`);
};

export const exportAsJSON = (findings) => {
  const data = mapFindings(findings);
  const json = JSON.stringify(data, null, 2);
  const blob = new Blob([json], { type: 'application/json' });
  downloadBlob(blob, `security-findings-${getDateStamp()}.json`);
};

export const exportAsPDF = (findings) => {
  const doc = new jsPDF({ orientation: 'landscape', unit: 'mm', format: 'a4' });

  doc.setFontSize(16);
  doc.text('Security Scan Findings', 14, 15);

  doc.setFontSize(9);
  doc.setTextColor(100);
  doc.text(`Generated: ${new Date().toLocaleString()}  |  Total findings: ${findings.length}`, 14, 22);

  const data = mapFindings(findings);
  const columns = [
    { header: 'Severity', dataKey: 'severity' },
    { header: 'Resource Type', dataKey: 'resource_type' },
    { header: 'Resource Name', dataKey: 'resource_name' },
    { header: 'Namespace', dataKey: 'namespace' },
    { header: 'Category', dataKey: 'category' },
    { header: 'Title', dataKey: 'title' },
    { header: 'Description', dataKey: 'description' },
    { header: 'Remediation', dataKey: 'remediation' },
  ];

  const severityColors = {
    critical: [220, 38, 38],
    high: [234, 88, 12],
    medium: [202, 138, 4],
    low: [37, 99, 235],
  };

  doc.autoTable({
    columns,
    body: data,
    startY: 27,
    styles: { fontSize: 7, cellPadding: 2 },
    headStyles: { fillColor: [107, 33, 168], textColor: 255, fontSize: 7 },
    columnStyles: {
      severity: { cellWidth: 18 },
      resource_type: { cellWidth: 22 },
      resource_name: { cellWidth: 30 },
      namespace: { cellWidth: 22 },
      category: { cellWidth: 22 },
      title: { cellWidth: 45 },
      description: { cellWidth: 60 },
      remediation: { cellWidth: 55 },
    },
    didParseCell: (hookData) => {
      if (hookData.column.dataKey === 'severity' && hookData.section === 'body') {
        const color = severityColors[hookData.cell.raw?.toLowerCase()];
        if (color) {
          hookData.cell.styles.textColor = color;
          hookData.cell.styles.fontStyle = 'bold';
        }
      }
    },
  });

  doc.save(`security-findings-${getDateStamp()}.pdf`);
};
