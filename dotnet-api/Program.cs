using OnboardingApi.Models;
using OnboardingApi.Services;
using Microsoft.AspNetCore.Mvc;
using System.Text.Json;
using PortCMIS.Client;
using PortCMIS.Client.Impl;


var builder = WebApplication.CreateBuilder(args);
builder.Services.AddHttpClient<AlfrescoService>();
builder.Services.AddSingleton<MongoService>();
builder.Services.AddSingleton<AlfrescoService>();
builder.Services.AddSingleton<AlfrescoPortCmisService>();

builder.Services.AddEndpointsApiExplorer();
builder.Services.AddSwaggerGen();
builder.Services.AddCors(options => options.AddPolicy("Gateway", policy =>
{ policy.WithOrigins("http://localhost:30010").AllowAnyMethod().AllowAnyHeader(); }));// this is to stop  blocked by CORS policy: No 'Access-Control-Allow-Origin'

var app = builder.Build();
app.UseSwagger();
app.UseSwaggerUI();

app.UseCors("Gateway");


// RESt api that handles saving into mongodb
app.MapPost("/onboarding", async (Client data, MongoService mongo) =>
{
    try
    {

        await mongo.Save(data);// Save 

        return Results.Ok(new { message = "Client saved successfully" });
    }
    catch (Exception ex)
    {
        Console.WriteLine("API Error: " + ex.Message);
        return Results.Problem("Mongo Post API Error : " + ex.Message);
    }
});

// alfresco api for file and metadata upload aswell as folder creation with respective information
app.MapPost("/onboarding/files", [Microsoft.AspNetCore.Authorization.AllowAnonymous]
async (HttpRequest request, AlfrescoService alfresco) => // switched here to http request because [fromform] causes anti forgery error
{


    // setting up cinfront and cinback in formfiles
    if (!request.HasFormContentType)
        return Results.BadRequest("Expected multipart/form-data");
    var formFiles = await request.ReadFormAsync();

    //setting up metadata here to be added to the new folder in alfresco
    var metadata = request.Query["metadata"];
    if (string.IsNullOrEmpty(metadata))
        return Results.BadRequest("Metadata is required");

    // Decode and deserialize JSON
    var decodedJson = Uri.UnescapeDataString(metadata!);
    var formData = JsonSerializer.Deserialize<Client>(decodedJson);




    var cinFront = formFiles.Files.GetFile("CinFront");
    var cinBack = formFiles.Files.GetFile("CinBack");

    var cinFolderId = await alfresco.CreateFolder(formData);

    //  Upload files into CIN folder
    if (cinFront != null)
        await alfresco.UploadFile(cinFront, cinFolderId, "CIN_Front.jpg");

    if (cinBack != null)
        await alfresco.UploadFile(cinBack, cinFolderId, "CIN_Back.jpg");

    return Results.Ok(new { message = $"Files uploaded under folder {formData.CIN}" });
}).RequireCors(cors => cors.AllowAnyOrigin().AllowAnyMethod().AllowAnyHeader()); //probably unecessary




app.MapGet("/cmis/folder", (AlfrescoPortCmisService cmis) =>
{
    try
    {
        var files = cmis.GetClientUploads();
        return Results.Ok(files);
    }
    catch (Exception ex)
    {
        Console.WriteLine(" API Error: " + ex.Message);
        return Results.Problem("Alfresco Get API Error : " + ex.Message);

    }


});

app.MapGet("/api/files/{*id}", async (string id, AlfrescoPortCmisService cmis) =>
{
    var _session = cmis.Session;
    id = Uri.UnescapeDataString(id);
    var doc = (IDocument)_session.GetObject(id);
    if (doc == null) return Results.NotFound();

    var stream = doc.GetContentStream().Stream;
    return Results.File(stream, doc.ContentStreamMimeType ?? "application/octet-stream", doc.Name);
});

/****ocr project api*/
app.MapPost("/ocrdata", [Microsoft.AspNetCore.Authorization.AllowAnonymous]
async (HttpRequest request, AlfrescoService alfresco) => // switched here to http request because [fromform] causes anti forgery error
{
    try
    {
        // 1. Read multipart form
        var form = await request.ReadFormAsync();

        var file = form.Files["file"];
        var ocrText = form["ocrText"].ToString();
        var ocrEngine = form["ocrEngine"].ToString();

        // 2. Validate
        if (file == null || file.Length == 0)
        {
            return Results.BadRequest("File is missing or empty");
        }

        if (string.IsNullOrWhiteSpace(ocrText))
        {
            return Results.BadRequest("OCR text is missing");
        }
        if (string.IsNullOrWhiteSpace(ocrEngine))
        {
            ocrEngine = "Unknown";
        }

        var nodeId = await alfresco.OcrUploadFile(file, ocrText, ocrEngine);

        return Results.Ok(new
        {
            message = "Uploaded to Alfresco",
            nodeId = nodeId,
            engine = ocrEngine
        });
    }
    catch (Exception ex)
    {
        return Results.Problem(ex.Message);
    }




}).RequireCors(cors => cors.AllowAnyOrigin().AllowAnyMethod().AllowAnyHeader());


app.Run();

