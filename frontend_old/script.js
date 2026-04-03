async function uploadPDF() {
    const file = document.getElementById("pdfFile").files[0];

    if (!file) return alert("Select PDF");

    const formData = new FormData();
    formData.append("file", file);

    try {
        const res = await fetch("http://localhost:8000/upload", {
            method: "POST",
            body: formData
        });

        const data = await res.json();
        console.log("Backend Output:", data);
        
        displayResults(data);
    } catch (err) {
        console.error("Upload failed", err);
        alert("Upload failed. Check console.");
    }
}

function displayResults(data) {
    if (!data.verification) return;

    // Show area
    document.getElementById("results-area").style.display = "block";

    // Populate Topics
    const topicsGrid = document.getElementById("topics-list");
    topicsGrid.innerHTML = "";

    data.verification.forEach(item => {
        // Only show if we actually mapped a topic and score > 0 (or show them all and let colour sort them out)
        if (item.score > 0) {
            const topicBox = document.createElement("div");
            topicBox.className = `topic-box ${item.color || 'red'}`;
            
            topicBox.innerHTML = `
                <span>${item.topic !== "None" ? item.topic : 'Generic Claim'}</span>
                <span class="topic-score">${item.score}/100</span>
            `;
            topicsGrid.appendChild(topicBox);
        }
    });

    // Populate Roadmap
    const roadmapGrid = document.getElementById("roadmap-list");
    roadmapGrid.innerHTML = "";
    
    if (data.roadmap && Array.isArray(data.roadmap)) {
        data.roadmap.forEach(step => {
            const stepDiv = document.createElement("div");
            stepDiv.className = "roadmap-step";
            stepDiv.innerHTML = `
                <h4>Step ${step.step}: ${step.topic}</h4>
                <p>${step.description}</p>
            `;
            roadmapGrid.appendChild(stepDiv);
        });
    } else {
        roadmapGrid.innerHTML = "<p>No roadmap could be generated.</p>";
    }
}