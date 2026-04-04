import React, { useMemo } from 'react';
import ReactFlow, { Background, Controls } from 'reactflow';
import 'reactflow/dist/style.css';

export default function RoadmapFlow({ roadmap }) {
  const nodes = useMemo(() => {
    return roadmap.map((step, idx) => ({
      id: `step-${idx}`,
      data: {
        label: (
          <div style={{ textAlign: 'left', padding: '10px 10px', fontSize: '12px' }}>
            <strong style={{ color: '#2c3e50', fontSize: '14px', display: 'block', marginBottom: '5px' }}>
              Step {step.step}: {step.topic}
            </strong>
            <p style={{ margin: '0', color: '#555', lineHeight: '1.4' }}>
              {step.description.substring(0, 80)}...
            </p>
            {step.recommended_paper && (
              <div style={{ marginTop: '8px', paddingTop: '8px', borderTop: '1px solid #dee2e6' }}>
                <strong style={{ color: '#3498db' }}>To Read:</strong>
                <br/>
                <a href={step.recommended_paper.url} target="_blank" rel="noopener noreferrer" style={{ color: '#3498db', textDecoration: 'none' }}>
                  {step.recommended_paper.title.substring(0, 45)}...
                </a>
              </div>
            )}
          </div>
        )
      },
      // Automatically place nodes downwards to form a sequence flow
      position: { x: 250, y: idx * 250 },
      style: { 
        width: 300, 
        background: '#fff', 
        border: '1px solid #bdc3c7', 
        borderRadius: '8px',
        boxShadow: '0 4px 6px rgba(0,0,0,0.05)'
      }
    }));
  }, [roadmap]);

  const edges = useMemo(() => {
    // Generate arrow edges linking node 1 -> 2, 2 -> 3, etc.
    const connections = [];
    for (let i = 0; i < roadmap.length - 1; i++) {
      connections.push({
        id: `edge-${i}-${i + 1}`,
        source: `step-${i}`,
        target: `step-${i + 1}`,
        animated: true, // Make the line visually flow downward
        style: { stroke: '#3498db', strokeWidth: 3 },
      });
    }
    return connections;
  }, [roadmap]);

  if (!roadmap || roadmap.length === 0) {
    return <p>No roadmap data to visualize.</p>;
  }

  return (
    <div style={{ height: '600px', width: '100%', border: '1px solid #ecf0f1', borderRadius: '8px', background: '#f8f9fa' }}>
      <ReactFlow nodes={nodes} edges={edges} fitView minimizeOnPan={false}>
        <Background color="#ecf0f1" gap={16} />
        <Controls />
      </ReactFlow>
    </div>
  );
}
